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


def guardar(state: dict) -> None:
    """Upsert del snapshot completo. Fail-safe: ante error, no rompe la request."""
    if not habilitado:
        return
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "insert into growth_state (id, data, updated_at)"
                " values (1, %s::jsonb, now())"
                " on conflict (id) do update set data = excluded.data,"
                " updated_at = now()",
                [json.dumps(state)],
            )
            conn.commit()
    except Exception as e:  # noqa: BLE001
        print("growth.pg save error:", e)


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


def guardar_normalizado(stores) -> None:
    """Vuelca saldos/pagos/vistas/reclamos a sus tablas (upsert idempotente).
    Fase 1: reescribe todas las filas (volumen de piloto). Fase 2 sería
    incremental. Fail-safe."""
    if not habilitado:
        return
    try:
        with _conn() as conn, conn.cursor() as cur:
            for dueno_id, cent in stores.saldos_rows():
                cur.execute(
                    "insert into growth_saldos (dueno_id, saldo_centimos, updated_at)"
                    " values (%s, %s, now()) on conflict (dueno_id) do update set"
                    " saldo_centimos = excluded.saldo_centimos, updated_at = now()",
                    [dueno_id, cent])

            for p in stores.pagos_rows():
                cur.execute(
                    "insert into growth_pagos"
                    f" ({', '.join(_PAGO_COLS)})"
                    f" values ({', '.join(['%s'] * len(_PAGO_COLS))})"
                    " on conflict (id) do update set estado = excluded.estado",
                    [p.get(c) for c in _PAGO_COLS])

            for id_, dia, n in stores.vistas_rows():
                cur.execute(
                    "insert into growth_vistas (id, dia, n) values (%s, %s, %s)"
                    " on conflict (id, dia) do update set n = excluded.n",
                    [id_, dia, n])

            for r in stores.reclamos_rows():
                cur.execute(
                    "insert into growth_reclamos"
                    f" ({', '.join(_RECLAMO_COLS)})"
                    f" values ({', '.join(['%s'] * len(_RECLAMO_COLS))})"
                    " on conflict (id) do update set"
                    " estado = excluded.estado, decidido_en = excluded.decidido_en,"
                    " validado_en = excluded.validado_en, validador = excluded.validador,"
                    " nota = excluded.nota",
                    [r.get(c) for c in _RECLAMO_COLS])
            conn.commit()
    except Exception as e:  # noqa: BLE001
        print("growth.pg guardar_normalizado error:", e)


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
    except Exception as e:  # noqa: BLE001
        print("growth.pg limpiar_todo error:", e)


def _fila_a_dict(cols: list[str], fila) -> dict:
    """Empareja una fila de la BD con sus columnas y normaliza fechas a ISO."""
    return {c: _iso(v) for c, v in zip(cols, fila)}
