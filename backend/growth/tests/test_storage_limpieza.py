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
        def __init__(self): self._existe = True
        def execute(self, sql):
            if "pichangol_bodega_productos" in sql:
                raise RuntimeError('relation "pichangol_bodega_productos" does not exist')
            self._existe = "select exists(select 1 from" in sql
        def fetchone(self):
            # Chequeo de referencia: la tabla tiene filas. Radiografía: usuario.
            return (True,) if self._existe else ("postgres", True)
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


def test_radiografia_distingue_limpio_de_ciego(monkeypatch):
    """Un '0 huérfanos' es ambiguo sin saber cuántos archivos alcanzó a ver el
    barrido: sin este dato no se distingue "todo limpio" de "no veo nada"."""
    class _Cur:
        def __init__(self): self.ultima = ""
        def execute(self, sql):
            self.ultima = sql
            if "storage.objects" in sql and "bucket_id, count" in sql:
                self._filas = [("canchas", 12), ("estados", 3)]
            elif "current_database" in sql:
                self._filas = [("postgres",)]
            else:
                self._filas = []
        def fetchone(self): return self._filas[0]
        def fetchall(self): return list(self._filas)
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
    assert r["radiografia"]["objetos_vistos"] == 15
    assert r["radiografia"]["objetos_por_bucket"]["canchas"] == 12


def test_radiografia_marca_cuando_no_puede_leer_storage(monkeypatch):
    """Si `storage.objects` no se puede leer (permisos/RLS), se marca con -1 en
    vez de reportar un tranquilizador 0."""
    class _Cur:
        def execute(self, sql):
            if "storage.objects" in sql:
                raise RuntimeError("permission denied for table objects")
            self._filas = [("postgres",)]
        def fetchone(self): return self._filas[0]
        def fetchall(self): return []
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
    assert r["radiografia"]["objetos_vistos"] == -1
    assert "permission denied" in r["radiografia"]["error_storage"]


def test_barrido_automatico_apagado_por_defecto():
    """No se automatiza un borrado hasta verificar la detección en la torre."""
    assert config.STORAGE_BARRIDO_AUTO is False


def test_arte_generado_compartido_es_intocable():
    """REGRESIÓN: los fondos de afiche (`afiches/`) los genera el backend y no
    pertenecen a ninguna fila. La primera versión los habría borrado por tratar
    toda carpeta del bucket como galería de una cancha."""
    assert sl._protegido("canchas", "afiches/fondo_tenis_lima.jpg")
    assert sl._borrar_objeto("canchas", "afiches/fondo_x.jpg") is False
    assert sl._protegido("canchas", "ilustraciones/il_entrenador_vacio.jpg")


def test_la_galeria_solo_alcanza_canchas_conocidas_y_borradas():
    """La consulta parte de un JOIN contra la tabla de canchas: una carpeta del
    sistema no puede colarse porque no existe una cancha con ese id, y una
    cancha VIVA tampoco porque se exige eliminada = true."""
    sql = sl._CONSULTAS["canchas_galeria"]
    assert "join pichangol_canchas" in sql
    assert "coalesce(c.eliminada, false) = true" in sql
    # Mismo criterio para la portada.
    assert "coalesce(c.eliminada, false) = true" in sl._CONSULTAS["canchas_portada"]


def test_cubre_todos_los_buckets_que_el_app_usa():
    """Ningún bucket que reciba subidas puede quedarse sin barrido: es como se
    llenó `canales` de archivos que nadie iba a borrar."""
    buckets = set()
    for sql in sl._CONSULTAS.values():
        for b in ("canchas", "estados", "productos", "chat", "canales",
                  "grupos", "verificacion"):
            if f"'{b}'" in sql:
                buckets.add(b)
    assert buckets == {"canchas", "estados", "productos", "chat", "canales",
                       "grupos", "verificacion"}


def test_avatar_sobrevive_solo_si_el_perfil_lo_apunta():
    """REGRESIÓN: antes se conservaba "el más nuevo" de cada usuario, así que la
    foto quedaba para siempre aunque el perfil se hubiera borrado o ya no la
    usara. Ahora sobrevive únicamente la que una fila de perfil referencia."""
    sql = sl._CONSULTAS["avatares"]
    assert "left join pichangol_perfiles" in sql
    assert "p.foto_url like" in sql
    assert "p.email is null" in sql
    # Ya no queda rastro de la regla vieja ("conserva el máximo por carpeta").
    assert "max(o2.name)" not in sql


def test_media_referenciada_se_cruza_por_url_no_por_nombre():
    """La media de posts y chats se cruza contra la URL guardada en su fila:
    adivinar el id desde el nombre del archivo es lo que falla cuando la ruta
    lleva timestamps o el hilo va saneado."""
    assert "p.media_url like" in sl._CONSULTAS["canales_posts"]
    assert "m.media_url like" in sl._CONSULTAS["chat_media"]
    assert "m.resp_media like" in sl._CONSULTAS["chat_media"]
    # La historia viva del chat no se toca: sólo entra lo que ningún mensaje
    # referencia, y los avatares van por su propia consulta.
    assert "not like 'perfiles/%'" in sl._CONSULTAS["chat_media"]


class _CurRef:
    """Cursor de prueba: la tabla de referencia indicada se ve VACÍA."""

    def __init__(self, vacias=(), filas=(("estados", "x.jpg"),)):
        self.vacias, self._filas, self._res = vacias, list(filas), None

    def execute(self, sql):
        if "select exists(select 1 from" in sql:
            tabla = sql.split("from ")[1].split(")")[0].strip()
            self._res = [(tabla not in self.vacias,)]
        elif "current_user" in sql:
            self._res = [("postgres", True)]
        elif "bucket_id, count" in sql:
            self._res = [("canchas", 14)]
        else:
            self._res = list(self._filas)

    def fetchone(self): return self._res[0]
    def fetchall(self): return list(self._res)
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _ConnRef:
    def __init__(self, cur): self._cur = cur
    def cursor(self): return self._cur
    def rollback(self): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_no_borra_cuando_la_tabla_de_referencia_se_ve_vacia(monkeypatch):
    """El caso peligroso: si RLS oculta las filas, "nadie referencia este
    archivo" deja de significar "es huérfano" y el barrido borraría lo VIVO.
    Ante esa duda no se borra nada de esa familia."""
    cur = _CurRef(vacias=("pichangol_canales", "pichangol_canal_posts"))
    monkeypatch.setattr(sl.pg, "habilitado", True)
    monkeypatch.setattr(sl.pg, "_conn", lambda: _ConnRef(cur))
    r = sl.analizar()
    assert r["familias"]["canales_portada"]["n"] == 0
    assert "no se puede distinguir" in r["familias"]["canales_portada"]["omitida"]
    # Una familia con su tabla visible sí se evalúa.
    assert "omitida" not in r["familias"]["estados"]


def test_limpiar_omite_esas_familias_sin_intentar_borrar(monkeypatch):
    cur = _CurRef(vacias=("pichangol_canales",))
    borrados = []
    monkeypatch.setattr(sl.pg, "habilitado", True)
    monkeypatch.setattr(sl.pg, "_conn", lambda: _ConnRef(cur))
    monkeypatch.setattr(sl, "_borrar_objeto",
                        lambda b, n: (borrados.append(f"{b}/{n}"), True)[1])
    r = sl.limpiar()
    assert r["omitidas"] >= 1
    assert all("canales" not in x for x in borrados)


def test_ref_del_proyecto_se_extrae_sin_exponer_credenciales():
    """Compara BD vs Storage sin tocar la contraseña de la cadena."""
    assert sl._ref_de_url("https://abcdefghijklmnop.supabase.co") == "abcdefghijklmnop"
    # Pooler: el ref viaja en el usuario.
    url = ("postgresql://postgres.abcdefghijklmnop:CLAVE@"
           "aws-0-sa-east-1.pooler.supabase.com:6543/postgres")
    assert sl._ref_de_url(url) == "abcdefghijklmnop"
    assert "CLAVE" not in sl._ref_de_url(url)
    assert sl._ref_de_url("") == ""


def test_la_torre_dice_siempre_a_que_ambiente_habla(monkeypatch):
    """Las torres de QAS y PRD son idénticas; confundirlas ya hizo creer que
    producción estaba sucia cuando lo sucio era dev. La página debe llevar el
    ambiente a la vista, sin depender de recordar la URL."""
    from propiedad import panel

    monkeypatch.setattr(config, "SUPABASE_URL", "https://abcdefghijklmnop.supabase.co")
    monkeypatch.setenv("PICHANGOL_ENTORNO", "PRD")
    html = panel.panel().body.decode()
    assert "PRD · abcdefghijklmnop" in html
    assert "__AMBIENTE__" not in html  # el marcador quedó reemplazado

    # Sin la env, el ref del proyecto ya identifica el ambiente.
    monkeypatch.delenv("PICHANGOL_ENTORNO")
    assert "abcdefghijklmnop" in panel.panel().body.decode()

    # Sin nada configurado, lo dice en vez de mostrar un vacío tranquilizador.
    monkeypatch.setattr(config, "SUPABASE_URL", "")
    assert "ambiente sin identificar" in panel.panel().body.decode()
