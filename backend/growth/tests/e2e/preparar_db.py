"""Prepara la base LOCAL del barrido web (CI y laptop): esquema extra + semilla.

`python -m db.migrar --local` deja el esquema base; las pantallas web leen
además tablas que en Supabase ya existen (perfiles, niveles, bonos, avisos,
bodega, boleadores…). Este script las crea desde `docs/piloto/` (tolerante:
un script que falla por algo propio de Supabase se anota y se sigue), crea
`pichangol_productos` (no tiene SQL en el repo: la creó el SQL Editor) y carga
`semilla.sql` con fechas RELATIVAS a hoy en Lima.

Uso (desde backend/growth):
    DATABASE_URL=postgresql://…@localhost:55432/e2e_ci \
        python tests/e2e/preparar_db.py --base http://localhost:8000

Se NIEGA a correr contra un host que no sea localhost (nunca QAS/PRD).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

AQUI = Path(__file__).resolve().parent
PILOTO = AQUI.parents[3] / "docs" / "piloto"

EXTRA = [
    "supabase_perfiles", "supabase_perfil_bio", "supabase_niveles", "supabase_bonos", "supabase_avisos",
    "supabase_espera", "supabase_lecturas", "supabase_chat_prefs", "supabase_agenda", "supabase_estados",
    "supabase_canales", "supabase_puntos_canjes", "supabase_canjes_web", "supabase_bodega",
    "supabase_bodega_moneda", "supabase_bodega_pedidos", "supabase_bodega_cuentas", "supabase_bodega_pago",
    "supabase_boleadores", "supabase_lugares_fotos", "supabase_canchas_cache", "supabase_places_consultas",
    "supabase_academia_operacion", "supabase_partidos_cupo", "supabase_partidos_juega_ya",
    "supabase_referidos", "supabase_mensajes_reply", "supabase_canchas_osm", "supabase_bloqueos",
]

PRODUCTOS = """
create table if not exists public.pichangol_productos (
  id text primary key,
  vendedor_email text not null default '',
  vendedor_nombre text not null default '',
  nombre text not null default '',
  descripcion text not null default '',
  precio numeric not null default 0,
  moneda text not null default 'S/',
  categoria text not null default '',
  foto_url text,
  stock integer,
  activo boolean not null default true,
  creado_en timestamptz not null default now()
);
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000", help="URL del servidor (fotos de la semilla)")
    a = ap.parse_args()
    url = os.getenv("DATABASE_URL", "")
    if (urlparse(url).hostname or "") not in ("localhost", "127.0.0.1", "::1"):
        print("Solo contra una base LOCAL (localhost)", file=sys.stderr)
        return 2
    import psycopg
    conn = psycopg.connect(url, autocommit=True, connect_timeout=8)
    conn.prepare_threshold = None
    for nombre in EXTRA:
        p = PILOTO / f"{nombre}.sql"
        if not p.exists():
            print(f"  (extra) falta {p.name}")
            continue
        try:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(p.read_text())
        except Exception as e:  # noqa: BLE001 — realtime/publicaciones de Supabase
            print(f"  (extra) {nombre}: {str(e).splitlines()[0]}")
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(PRODUCTOS)
    sql = (AQUI / "semilla.sql").read_text().replace("{{BASE}}", a.base.rstrip("/"))
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(sql)
    with conn.cursor() as cur:
        cur.execute("select count(*) from pichangol_canchas where id like 'demo\\_%'")
        nc = cur.fetchone()[0]
        cur.execute("select count(*) from pichangol_reservas where id like 'demo\\_%'")
        nr = cur.fetchone()[0]
    print(f"Semilla e2e lista: {nc} canchas, {nr} reservas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
