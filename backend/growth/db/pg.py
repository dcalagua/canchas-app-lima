"""Persistencia en Supabase/Postgres.

Dos capas conviven durante la migración por fases:

1. **Snapshot JSON** (`growth_state`, una fila): guarda TODO el estado del growth.
   Robusto y de bajo riesgo; sigue siendo el respaldo completo.
2. **Tablas normalizadas** para lo CRÍTICO (plata + impacto + reclamos):
   `growth_saldos`, `growth_pagos`, `growth_vistas`, `growth_reclamos`. Se
   escriben junto al snapshot y, al cargar, son la fuente de verdad de esas
   colecciones si tienen datos (si están vacías —primer deploy— se respeta el
   snapshot y se hace *backfill*). Permiten consultar/auditar en SQL y no
   depender del blob monolítico para lo sensible.

Si `DATABASE_URL` no está, todo queda inactivo y el servicio corre 100% en
memoria (fail-safe). Nada aquí rompe una request: los errores se tragan y se
loguean.

`DATABASE_URL`: Supabase → Database → Connection string (pooler 6543, sslmode=require).
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime

DATABASE_URL = os.getenv("DATABASE_URL", "")
habilitado = bool(DATABASE_URL)

_DDL_SNAPSHOT = (
    "create table if not exists growth_state ("
    " id int primary key,"
    " data jsonb not null,"
    " updated_at timestamptz not null default now())"
)

# Tablas normalizadas (fase 1). `if not exists` = idempotente y seguro de repetir.
_DDL_TABLAS = [
    """create table if not exists growth_saldos (
        dueno_id text primary key,
        saldo_centimos bigint not null default 0,
        updated_at timestamptz not null default now())""",
    """create table if not exists growth_pagos (
        id bigint primary key,
        tipo text not null,
        monto_centimos bigint not null,
        moneda text not null default 'PEN',
        estado text not null,
        dueno_id text,
        culqi_charge_id text,
        email text,
        concepto text,
        creado_en timestamptz not null)""",
    "create index if not exists idx_growth_pagos_dueno on growth_pagos (dueno_id)",
    """create table if not exists growth_vistas (
        id text not null,
        dia date not null,
        n integer not null default 0,
        primary key (id, dia))""",
    """create table if not exists growth_reclamos (
        id bigint primary key,
        cancha_id text not null,
        solicitante_id text not null,
        nombre_local text not null,
        codigo text not null,
        estado text not null,
        telefono_contacto text,
        dni text,
        nombre_titular text,
        ruc text,
        razon_social text,
        relacion text,
        lat double precision,
        lng double precision,
        solicitante_lat double precision,
        solicitante_lng double precision,
        creado_en timestamptz not null,
        decidido_en timestamptz,
        validado_en timestamptz,
        validador text,
        nota text)""",
    "create index if not exists idx_growth_reclamos_cancha on growth_reclamos (cancha_id)",
]

# Columnas de reclamos, en el orden en que se leen/escriben.
_RECLAMO_COLS = [
    "id", "cancha_id", "solicitante_id", "nombre_local", "codigo", "estado",
    "telefono_contacto", "dni", "nombre_titular", "ruc", "razon_social",
    "relacion", "lat", "lng", "solicitante_lat", "solicitante_lng",
    "creado_en", "decidido_en", "validado_en", "validador", "nota",
]
_PAGO_COLS = [
    "id", "tipo", "monto_centimos", "moneda", "estado", "dueno_id",
    "culqi_charge_id", "email", "concepto", "creado_en",
]


def _conn():
    import psycopg  # import perezoso: solo si hay DATABASE_URL
    conn = psycopg.connect(DATABASE_URL, connect_timeout=8)
    # Sin prepared statements: compatible con el pooler en modo transacción
    # (pgbouncer) sin errores de "prepared statement already exists".
    conn.prepare_threshold = None
    return conn


# ── Pool pequeño de conexiones (web pública, sep-2026) ───────────────────────
# Cada `_conn()` abre una conexión NUEVA al pooler de Supabase (TLS + handshake
# ≈ 300-500 ms). La ficha de reserva hacía 4-5 consultas seguidas → 2 s solo
# en conectar. `conexion()` reutiliza hasta POOL_MAX conexiones abiertas
# (transacción por uso: commit al salir bien, rollback + descartar si falló;
# las inactivas > POOL_TTL_SEG se cierran, el pooler las corta igual).
import threading as _th
import time as _time
from contextlib import contextmanager as _cm

POOL_MAX = 8
POOL_TTL_SEG = 240
_pool: list = []  # [(conn, devuelta_en)]
_pool_lock = _th.Lock()


def _tomar():
    with _pool_lock:
        while _pool:
            conn, ts = _pool.pop()
            if conn.closed or _time.time() - ts > POOL_TTL_SEG:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass
                continue
            return conn
    return _nueva_pool()


def _nueva_pool():
    conn = _conn()
    conn.autocommit = True  # transacción perezosa (ver `_ConexionPerezosa`)
    return conn


def _devolver(conn) -> None:
    with _pool_lock:
        if not conn.closed and len(_pool) < POOL_MAX:
            _pool.append((conn, _time.time()))
            return
    try:
        conn.close()
    except Exception:  # noqa: BLE001
        pass


# ── Transacción PEREZOSA (1-oct-2026, "cada clic demora mucho") ─────────────
# El backend corre en Railway us-west2 y la base de PRD en São Paulo: cada ida y
# vuelta cuesta ~180 ms. psycopg abre una transacción implícita (BEGIN = 1 viaje)
# antes de la 1.ª consulta y `commit()` al salir es otro viaje → una lectura
# simple costaba 3 viajes (~550 ms) y una página con 3 bloques, ~1,7 s. Ahora la
# conexión del pool va en AUTOCOMMIT y la transacción se abre recién con la
# primera ESCRITURA (o `FOR UPDATE`): las lecturas cuestan 1 viaje. Mismo
# resultado que antes bajo READ COMMITTED (cada SELECT ya veía su propia foto;
# un SELECT sin FOR UPDATE no bloqueaba nada); lo atómico (varias escrituras,
# FOR UPDATE + UPDATE) sigue en UNA transacción hasta `commit()` o el final.
import re as _re

_RE_LECTURA = _re.compile(r"^\s*(select|with|show|values)\b", _re.I)
_RE_ESCRIBE = _re.compile(r"\b(insert|update|delete|merge|truncate|create|alter|drop|grant|revoke|lock|for\s+update|for\s+share|for\s+no\s+key)\b", _re.I)


def es_lectura(sql) -> bool:
    texto = sql if isinstance(sql, str) else str(sql)
    return bool(_RE_LECTURA.match(texto)) and not _RE_ESCRIBE.search(texto)


class _CursorPerezoso:
    def __init__(self, conx, cur):
        self._conx, self._cur = conx, cur

    def execute(self, sql, params=None, **kw):
        if not es_lectura(sql):
            self._conx._abrir()
        return self._cur.execute(sql, params, **kw) if params is not None else self._cur.execute(sql, **kw)

    def executemany(self, sql, params_seq, **kw):
        self._conx._abrir()
        return self._cur.executemany(sql, params_seq, **kw)

    def __getattr__(self, nombre):
        return getattr(self._cur, nombre)

    def __iter__(self):
        return iter(self._cur)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        try:
            self._cur.close()
        except Exception:  # noqa: BLE001
            pass
        return False


class _ConexionPerezosa:
    """Envuelve una conexión en autocommit; `commit()`/`rollback()` solo viajan
    si de verdad hay una transacción abierta."""

    def __init__(self, conn):
        self._conn, self._en_tx = conn, False

    def _abrir(self):
        if not self._en_tx:
            self._conn.execute("BEGIN")
            self._en_tx = True

    def cursor(self, *a, **k):
        return _CursorPerezoso(self, self._conn.cursor(*a, **k))

    def execute(self, sql, params=None, **kw):
        if not es_lectura(sql):
            self._abrir()
        return self._conn.execute(sql, params, **kw) if params is not None else self._conn.execute(sql, **kw)

    def commit(self):
        if self._en_tx:
            self._en_tx = False
            self._conn.execute("COMMIT")

    def rollback(self):
        if self._en_tx:
            self._en_tx = False
            self._conn.execute("ROLLBACK")

    def __getattr__(self, nombre):
        return getattr(self._conn, nombre)


@_cm
def conexion():
    """`with pg.conexion() as conn:` — conexión del pool; commit al salir,
    rollback y descarte si hubo error. Reemplaza a `with _conn() as conn`
    (que cierra la conexión) en los caminos calientes de la web. Transacción
    perezosa: ver `_ConexionPerezosa`."""
    crudo = _tomar()
    conn = _ConexionPerezosa(crudo)
    try:
        yield conn
    except BaseException:
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        try:
            crudo.close()
        except Exception:  # noqa: BLE001
            pass
        raise
    else:
        try:
            conn.commit()
        except Exception:  # noqa: BLE001
            try:
                crudo.close()
            except Exception:  # noqa: BLE001
                pass
            raise
        _devolver(crudo)


def _mantener_tibias() -> None:
    """Cada 60 s hace `SELECT 1` en las conexiones del pool para que no caduquen
    (abrir una nueva hacia São Paulo = TLS + login ≈ 1 s: era el "primer clic
    lento" tras unos minutos sin visitas) y deja al menos 2 abiertas."""
    while True:
        _time.sleep(60)
        try:
            with _pool_lock:
                lote = list(_pool)
                _pool.clear()
            vivas = []
            for c, _ts in lote:
                try:
                    c.execute("SELECT 1")
                    vivas.append((c, _time.time()))
                except Exception:  # noqa: BLE001
                    try:
                        c.close()
                    except Exception:  # noqa: BLE001
                        pass
            while len(vivas) < 2:
                try:
                    vivas.append((_nueva_pool(), _time.time()))
                except Exception:  # noqa: BLE001
                    break
            with _pool_lock:
                for v in vivas:
                    if len(_pool) < POOL_MAX:
                        _pool.append(v)
                    else:
                        v[0].close()
        except Exception as ex:  # noqa: BLE001
            print(f"[pool] tibias: {ex}", flush=True)


_tibias_hilo = None


def iniciar_tibias() -> None:
    global _tibias_hilo
    if not habilitado or (_tibias_hilo is not None and _tibias_hilo.is_alive()):
        return
    _tibias_hilo = _th.Thread(target=_mantener_tibias, name="pcg-pool", daemon=True)
    _tibias_hilo.start()


def _iso(v):
    """Normaliza fechas/horas de la BD a ISO (str), para reusar los parsers del
    store (`_pago_from`/`_reclamo_from`) que esperan strings ISO como el snapshot."""
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def init_y_cargar() -> dict | None:
    """Crea las tablas si no existen y devuelve el último snapshot (o None)."""
    if not habilitado:
        return None
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(_DDL_SNAPSHOT)
            for ddl in _DDL_TABLAS:
                cur.execute(ddl)
            cur.execute("select data from growth_state where id = 1")
            row = cur.fetchone()
            conn.commit()
            return row[0] if row else None
    except Exception as e:  # noqa: BLE001
        print("growth.pg init/load error:", e)
        return None


_ultimo_hash: str | None = None   # huella del último snapshot escrito (evita reescribir lo mismo)
_hash_lock = _th.Lock()


def _huella(texto: str) -> str:
    import hashlib
    return hashlib.blake2b(texto.encode("utf-8"), digest_size=16).hexdigest()


def guardar(state: dict, *, forzar: bool = False) -> bool:
    """Upsert del snapshot completo. Fail-safe: ante error, no rompe la request.

    LENTITUD RESUELTA (queja del director, 25-sep-2026: "mucho se demora para
    agregar un simple equipo, y lo mismo sucede en todo el sistema"): antes
    CADA POST abría una conexión nueva (TLS ≈ 300-500 ms) y reescribía el
    snapshot entero aunque nada hubiera cambiado. Ahora usa el pool y solo
    escribe si la huella del JSON cambió desde la última escritura.
    Devuelve True si escribió."""
    global _ultimo_hash
    if not habilitado:
        return False
    try:
        t0 = _time.time()
        texto = json.dumps(state)
        h = _huella(texto)
        if not forzar and h == _ultimo_hash:
            return False
        with conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "insert into growth_state (id, data, updated_at)"
                " values (1, %s::jsonb, now())"
                " on conflict (id) do update set data = excluded.data,"
                " updated_at = now()",
                [texto],
            )
        with _hash_lock:
            _ultimo_hash = h
        ms = int((_time.time() - t0) * 1000)
        if ms > 400:
            print(f"[persistir] snapshot {len(texto) // 1024} KB en {ms} ms", flush=True)
        return True
    except Exception as e:  # noqa: BLE001
        print("growth.pg save error:", e)
        return False


def cargar_normalizado(stores) -> None:
    """Carga las 4 tablas normalizadas SOBRE el estado ya cargado del snapshot.
    Cada colección se sobreescribe SOLO si su tabla tiene datos (así el primer
    deploy —tablas vacías— conserva lo del snapshot y luego se hace backfill)."""
    if not habilitado:
        return
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("select dueno_id, saldo_centimos from growth_saldos")
            saldos = cur.fetchall()
            if saldos:
                stores.cargar_saldos_rows(saldos)

            cur.execute(
                f"select {', '.join(_PAGO_COLS)} from growth_pagos order by id")
            pagos = cur.fetchall()
            if pagos:
                stores.cargar_pagos_rows(
                    [_fila_a_dict(_PAGO_COLS, r) for r in pagos])

            cur.execute("select id, dia, n from growth_vistas")
            vistas = cur.fetchall()
            if vistas:
                stores.cargar_vistas_rows(
                    [(r[0], _iso(r[1]), r[2]) for r in vistas])

            cur.execute(
                f"select {', '.join(_RECLAMO_COLS)} from growth_reclamos order by id")
            reclamos = cur.fetchall()
            if reclamos:
                stores.cargar_reclamos_rows(
                    [_fila_a_dict(_RECLAMO_COLS, r) for r in reclamos])
            conn.commit()
    except Exception as e:  # noqa: BLE001
        print("growth.pg cargar_normalizado error:", e)


_norm_huellas: dict[str, dict] = {"saldos": {}, "pagos": {}, "vistas": {}, "reclamos": {}}


def _solo_cambiadas(tabla: str, filas: list, clave) -> list:
    """Filtra las filas cuya huella cambió desde la última escritura (o nuevas)."""
    vistas = _norm_huellas[tabla]
    out, nuevas = [], {}
    for f in filas:
        k = clave(f)
        h = _huella(json.dumps(f, sort_keys=True, default=str))
        nuevas[k] = h
        if vistas.get(k) != h:
            out.append((k, h, f))
    return out


def guardar_normalizado(stores) -> None:
    """Vuelca saldos/pagos/vistas/reclamos a sus tablas (upsert idempotente).
    INCREMENTAL (25-sep-2026): antes reescribía TODAS las filas en cada POST,
    una ida y vuelta por fila (cientos de pagos × ~20 ms = segundos en cada
    guardado del sistema). Ahora recuerda la huella de cada fila escrita en
    este proceso y solo manda las nuevas o cambiadas, en lote (`executemany`);
    tras un arranque la primera pasada escribe todo una vez (backfill). Fail-safe."""
    if not habilitado:
        return
    try:
        t0 = _time.time()
        saldos = _solo_cambiadas("saldos", [list(r) for r in stores.saldos_rows()], lambda r: r[0])
        pagos = _solo_cambiadas("pagos", stores.pagos_rows(), lambda p: p.get("id"))
        vistas = _solo_cambiadas("vistas", [list(r) for r in stores.vistas_rows()], lambda r: (r[0], r[1]))
        reclamos = _solo_cambiadas("reclamos", stores.reclamos_rows(), lambda r: r.get("id"))
        n = len(saldos) + len(pagos) + len(vistas) + len(reclamos)
        if not n:
            return
        with conexion() as conn, conn.cursor() as cur:
            if saldos:
                cur.executemany(
                    "insert into growth_saldos (dueno_id, saldo_centimos, updated_at)"
                    " values (%s, %s, now()) on conflict (dueno_id) do update set"
                    " saldo_centimos = excluded.saldo_centimos, updated_at = now()",
                    [(f[0], f[1]) for _, _, f in saldos])
            if pagos:
                cur.executemany(
                    "insert into growth_pagos"
                    f" ({', '.join(_PAGO_COLS)})"
                    f" values ({', '.join(['%s'] * len(_PAGO_COLS))})"
                    " on conflict (id) do update set estado = excluded.estado",
                    [[p.get(c) for c in _PAGO_COLS] for _, _, p in pagos])
            if vistas:
                cur.executemany(
                    "insert into growth_vistas (id, dia, n) values (%s, %s, %s)"
                    " on conflict (id, dia) do update set n = excluded.n",
                    [(f[0], f[1], f[2]) for _, _, f in vistas])
            if reclamos:
                cur.executemany(
                    "insert into growth_reclamos"
                    f" ({', '.join(_RECLAMO_COLS)})"
                    f" values ({', '.join(['%s'] * len(_RECLAMO_COLS))})"
                    " on conflict (id) do update set"
                    " estado = excluded.estado, decidido_en = excluded.decidido_en,"
                    " validado_en = excluded.validado_en, validador = excluded.validador,"
                    " nota = excluded.nota",
                    [[r.get(c) for c in _RECLAMO_COLS] for _, _, r in reclamos])
        # Solo tras el commit (al salir del `with`) damos las filas por escritas.
        for tabla, cambios in (("saldos", saldos), ("pagos", pagos), ("vistas", vistas), ("reclamos", reclamos)):
            for k, h, _ in cambios:
                _norm_huellas[tabla][k] = h
        ms = int((_time.time() - t0) * 1000)
        if ms > 400:
            print(f"[persistir] tablas normalizadas: {n} filas en {ms} ms", flush=True)
    except Exception as e:  # noqa: BLE001
        print("growth.pg guardar_normalizado error:", e)


# ── Persistencia en segundo plano (25-sep-2026) ──────────────────────────────
# El middleware de main.py ya NO guarda dentro de la request (bloqueaba el event
# loop y la respuesta esperaba a Supabase): marca "hay cambios" y un hilo único
# escribe con un pequeño rebote (varios POST seguidos = una sola escritura).
_pers_evento = _th.Event()
_pers_hilo: _th.Thread | None = None
_pers_lock = _th.Lock()
_pers_stores = None
PERSISTIR_REBOTE_SEG = 0.25


def persistir_ahora(stores) -> None:
    """Snapshot + tablas, sincrónico (retornos de pasarela, apagado)."""
    guardar(stores.to_state())
    guardar_normalizado(stores)


def _pers_bucle() -> None:
    while True:
        _pers_evento.wait()
        _time.sleep(PERSISTIR_REBOTE_SEG)
        _pers_evento.clear()
        try:
            if _pers_stores is not None:
                persistir_ahora(_pers_stores)
        except Exception as e:  # noqa: BLE001
            print("growth.pg persistencia en segundo plano:", e)


def persistir_en_segundo_plano(stores) -> None:
    """Pide guardar sin bloquear la request. Fail-safe; sin DATABASE_URL no hace nada."""
    global _pers_hilo, _pers_stores
    if not habilitado:
        return
    _pers_stores = stores
    with _pers_lock:
        if _pers_hilo is None or not _pers_hilo.is_alive():
            _pers_hilo = _th.Thread(target=_pers_bucle, name="pcg-persistir", daemon=True)
            _pers_hilo.start()
    _pers_evento.set()


def hay_persistencia_pendiente() -> bool:
    return _pers_evento.is_set()


def limpiar_todo() -> None:
    """VIRGEN TOTAL a nivel BD: vacía el snapshot Y todas las tablas normalizadas
    (saldos, pagos, vistas, reclamos). IMPRESCINDIBLE: como `guardar_normalizado`
    solo hace upsert (nunca borra filas), sin esto un reinicio RECARGA los reclamos
    desde `growth_reclamos` aunque el snapshot esté vacío. Fail-safe."""
    if not habilitado:
        return
    try:
        with _conn() as conn, conn.cursor() as cur:
            for t in ("growth_reclamos", "growth_pagos", "growth_vistas",
                      "growth_saldos", "growth_state"):
                cur.execute(f"truncate table {t}")
            conn.commit()
        global _ultimo_hash
        _ultimo_hash = None
        for d in _norm_huellas.values():
            d.clear()
    except Exception as e:  # noqa: BLE001
        print("growth.pg limpiar_todo error:", e)


def _fila_a_dict(cols: list[str], fila) -> dict:
    """Empareja una fila de la BD con sus columnas y normaliza fechas a ISO."""
    return {c: _iso(v) for c, v in zip(cols, fila)}
