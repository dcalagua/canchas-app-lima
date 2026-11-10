"""Runner de MIGRACIONES VERSIONADAS (`backend/growth/migraciones/NNNN_*.sql`).

Antes había ~80 scripts sueltos en `docs/piloto/` sin registro de qué corrió
en cada base. Ahora cada cambio de esquema es un archivo numerado, idempotente,
que se registra en `cl_schema_migraciones`. Los mismos archivos sirven para
correrlos a mano en el SQL Editor de Supabase (convención del repo).

Uso (desde backend/growth):
    python -m db.migrar --estado           # qué falta en DATABASE_URL
    python -m db.migrar                    # aplica lo pendiente
    python -m db.migrar --local            # Docker: roles de Supabase + esquema
                                           # base de docs/piloto + pendientes

`--local` se NIEGA a correr contra un host que no sea localhost (nunca contra
Supabase QAS/PRD por accidente).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

RAIZ = Path(__file__).resolve().parent.parent
DIR = RAIZ / "migraciones"
PILOTO = RAIZ.parent.parent / "docs" / "piloto"

# Esquema base que en Supabase ya existe (solo para la base LOCAL).
BASE_LOCAL = [
    "supabase_QAS_completo", "supabase_canchas_columnas_completas", "supabase_barrio",
    "supabase_precio_turno", "supabase_hora_feliz", "supabase_horas_felices",
    "supabase_descuentos_slot", "supabase_sena_y_medio_pago", "supabase_medio_pago",
    "supabase_reservas_grupo", "supabase_reservas_cargo", "supabase_servicios_extra",
    "supabase_fidelidad", "supabase_cancelaciones", "supabase_reserva_manual",
    "supabase_ai_marketing",
]

_PATRON = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


def archivos() -> list[tuple[str, Path]]:
    out = []
    for p in sorted(DIR.glob("*.sql")):
        m = _PATRON.match(p.name)
        if m:
            out.append((m.group(1), p))
    return out


def _conectar(url: str):
    import psycopg
    conn = psycopg.connect(url, connect_timeout=8, autocommit=True)
    conn.prepare_threshold = None
    return conn


def aplicadas(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("select to_regclass('public.cl_schema_migraciones')")
        if cur.fetchone()[0] is None:
            return set()
        cur.execute("select version from public.cl_schema_migraciones")
        return {r[0] for r in cur.fetchall()}


def _ejecutar(conn, sql: str) -> None:
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(sql)


def es_local(url: str) -> bool:
    return (urlparse(url).hostname or "") in ("localhost", "127.0.0.1", "::1")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--estado", action="store_true")
    ap.add_argument("--local", action="store_true")
    a = ap.parse_args(argv)
    url = os.getenv("DATABASE_URL", "")
    if not url:
        print("Falta DATABASE_URL", file=sys.stderr)
        return 2
    if a.local and not es_local(url):
        print("--local solo contra localhost (protección de QAS/PRD)", file=sys.stderr)
        return 2
    conn = _conectar(url)
    if a.local:
        _ejecutar(conn, (DIR / "local" / "0000_roles_supabase.sql").read_text())
        for nombre in BASE_LOCAL:
            try:
                _ejecutar(conn, (PILOTO / f"{nombre}.sql").read_text())
            except Exception as e:  # noqa: BLE001 — publicaciones de realtime, etc.
                print(f"  (base) {nombre}: {str(e).splitlines()[0]}")
    hechas = aplicadas(conn)
    pendientes = [(v, p) for v, p in archivos() if v not in hechas]
    if a.estado:
        for v, p in archivos():
            print(f"{'✓' if v in hechas else '·'} {p.name}")
        return 0
    for v, p in pendientes:
        print(f"→ {p.name}")
        _ejecutar(conn, p.read_text())
    print(f"OK: {len(pendientes)} aplicada(s); total {len(aplicadas(conn))}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
