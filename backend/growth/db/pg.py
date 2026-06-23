"""Persistencia por snapshot en Supabase/Postgres.

Guarda TODO el estado del growth como un JSON en la tabla `growth_state` (una
fila). Es robusto y de bajo riesgo para el piloto: sobrevive reinicios sin
reescribir cada operación a SQL. Si `DATABASE_URL` no está, queda inactivo y el
servicio sigue 100% en memoria (fail-safe).

`DATABASE_URL`: cadena de conexión de Supabase (Project Settings → Database →
Connection string / URI; usar el **pooler**, puerto 6543, con `sslmode=require`).
"""

from __future__ import annotations

import json
import os

DATABASE_URL = os.getenv("DATABASE_URL", "")
habilitado = bool(DATABASE_URL)

_DDL = (
    "create table if not exists growth_state ("
    " id int primary key,"
    " data jsonb not null,"
    " updated_at timestamptz not null default now())"
)


def _conn():
    import psycopg  # import perezoso: solo si hay DATABASE_URL
    return psycopg.connect(DATABASE_URL, connect_timeout=8)


def init_y_cargar() -> dict | None:
    """Crea la tabla si no existe y devuelve el último snapshot (o None)."""
    if not habilitado:
        return None
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(_DDL)
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
