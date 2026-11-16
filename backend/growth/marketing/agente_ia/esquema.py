"""Esquema del AI Marketing Agent (tablas `ai_*`).

Mismo DDL que `docs/piloto/supabase_ai_marketing.sql` (partes 1-8; el test
`test_agente_ia_esquema` vigila que no se desalineen). Idempotente: el backend lo
corre al arrancar, igual que `db/pg.py` crea `growth_*`. Las columnas de
atribución de `pichangol_reservas` (parte 9) NO se tocan desde aquí: van en el
SQL manual, y el código detecta si ya existen (`columnas_atribucion`).
"""
from __future__ import annotations

import threading
import time

DDL: list[str] = [
    """create table if not exists ai_marketing_campaigns (
  id text primary key,
  nombre text not null,
  objetivo text not null check (objetivo in ('reservas','usuarios','promo_cancha','captar_duenos',
                                             'promo_zona','interaccion','trafico','promo_real')),
  audiencia text not null check (audiencia in ('jugadores','duenos','general')),
  pais text not null default 'PE',
  zona text,
  kpi text not null,
  kpi_meta numeric,
  inicio date,
  fin date,
  estado text not null default 'activa' check (estado in ('borrador','activa','pausada','cerrada')),
  creada_por text not null default 'agente',
  created_at timestamptz not null default now()
)""",
    """create table if not exists ai_marketing_strategy (
  id text primary key,
  fecha date not null,
  pais text not null default 'PE',
  snapshot jsonb not null,
  candidatas jsonb not null default '[]'::jsonb,
  oportunidades jsonb not null default '[]'::jsonb,
  insights_usados jsonb not null default '[]'::jsonb,
  fuente text not null default 'reglas',      -- 'ia' | 'reglas'
  created_at timestamptz not null default now(),
  unique (fecha, pais)
)""",
    """create table if not exists ai_content (
  id text primary key,
  codigo text not null unique,                -- short-link /go/{codigo}
  campaign_id text references ai_marketing_campaigns(id),
  strategy_id text references ai_marketing_strategy(id),
  oportunidad jsonb not null default '{}'::jsonb,
  content_type text not null check (content_type in ('post','story','reel','carrusel','encuesta','pregunta','meme','educativo')),
  platform text not null check (platform in ('facebook','instagram','whatsapp','push')),
  audiencia text not null,
  objetivo text not null,
  kpi text not null,
  pais text not null default 'PE',
  zona text,
  title text,
  subtitle text,
  etiqueta text,
  body text not null,
  call_to_action text,
  hashtags jsonb not null default '[]'::jsonb,
  link_url text,
  destino_url text,
  media_url text,
  media_origen text check (media_origen in ('foto_real','foto_dueno','diseno','ia_conceptual','ia_ambientada','video_ia')),
  hechos jsonb not null default '{}'::jsonb,
  validacion jsonb not null default '{}'::jsonb,
  fuente text not null default 'reglas',
  status text not null default 'DRAFT',
  scheduled_at timestamptz,
  published_at timestamptz,
  external_post_id text,
  permalink text,
  error text,
  intentos int not null default 0,
  revisado_por text,
  revisado_en timestamptz,
  motivo_rechazo text,
  huella text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
)""",
    """alter table ai_content drop constraint if exists ai_content_media_origen_check""",
    """alter table ai_content add constraint ai_content_media_origen_check check (media_origen in
  ('foto_real','foto_dueno','diseno','ia_conceptual','ia_ambientada','video_ia'))""",
    """alter table ai_content drop constraint if exists ai_content_status_check""",
    """alter table ai_content add constraint ai_content_status_check check (status in
  ('DRAFT','PENDING_APPROVAL','APPROVED','PUBLISHING','PUBLISHED','REJECTED','FAILED','CANCELLED'))""",
    """create index if not exists idx_ai_content_status on ai_content (status, scheduled_at)""",
    """create index if not exists idx_ai_content_creado on ai_content (created_at desc)""",
    """create table if not exists ai_content_targets (
  content_id text not null references ai_content(id) on delete cascade,
  cancha_id text not null,
  rol text not null default 'evidencia' check (rol in ('evidencia','destacada')),
  primary key (content_id, cancha_id)
)""",
    """create table if not exists ai_content_clicks (
  id bigserial primary key,
  content_id text not null references ai_content(id) on delete cascade,
  visitante text,                              -- hash anónimo (sin IP ni PII)
  creado timestamptz not null default now()
)""",
    """create index if not exists idx_ai_clicks_content on ai_content_clicks (content_id, creado)""",
    """create table if not exists ai_content_performance (
  content_id text not null references ai_content(id) on delete cascade,
  ventana text not null check (ventana in ('1h','24h','72h','7d','28d')),
  alcance int, impresiones int, interacciones int, reacciones int,
  comentarios int, compartidos int, clics int, reproducciones int,
  clics_link int, reservas_atribuidas int, ingresos_atribuidos numeric,
  engagement_rate numeric,
  raw jsonb not null default '{}'::jsonb,
  medido_en timestamptz not null default now(),
  primary key (content_id, ventana)
)""",
    """create table if not exists ai_insights (
  id text primary key,
  enunciado text not null,
  dimension text not null,
  valor text not null,
  metrica text not null,
  efecto numeric not null,
  muestras int not null,
  confianza numeric not null,
  evidencia jsonb not null default '[]'::jsonb,
  vigente boolean not null default true,
  created_at timestamptz not null default now()
)""",
    """create index if not exists idx_ai_insights_vigente on ai_insights (vigente)""",
    """create table if not exists ai_agent_logs (
  id bigserial primary key,
  agente text not null,
  accion text not null,
  content_id text,
  strategy_id text,
  nivel text not null default 'info' check (nivel in ('info','warn','error')),
  detalle jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
)""",
    """create index if not exists idx_ai_logs_creado on ai_agent_logs (created_at desc)""",
    """alter table ai_marketing_campaigns enable row level security""",
    """alter table ai_marketing_strategy  enable row level security""",
    """alter table ai_content             enable row level security""",
    """alter table ai_content_targets     enable row level security""",
    """alter table ai_content_clicks      enable row level security""",
    """alter table ai_content_performance enable row level security""",
    """alter table ai_insights            enable row level security""",
    """alter table ai_agent_logs          enable row level security""",
]

_lock = threading.Lock()
_listo = False
_fallo_en = 0.0                 # último intento fallido (no reintentar el DDL en cada request)
REINTENTO_S = 300
_cols_reservas: set[str] | None = None
_cols_leidas_en = 0.0
COLS_TTL_S = 600                # tras correr el SQL manual, se detecta sin reiniciar el backend


def asegurar() -> bool:
    """Crea las tablas `ai_*` una sola vez por proceso. False si no hay base."""
    global _listo, _fallo_en
    from db import pg
    if _listo:
        return True
    if not pg.habilitado or time.time() - _fallo_en < REINTENTO_S:
        return False
    with _lock:
        if _listo:
            return True
        try:
            with pg._conn() as c, c.cursor() as cur:
                for ddl in DDL:
                    cur.execute(ddl)
                c.commit()
            _listo = True
        except Exception as e:  # noqa: BLE001
            _fallo_en = time.time()
            print(f"[agente_ia] no se pudo crear el esquema: {str(e)[:200]}", flush=True)
    return _listo


def columnas_atribucion() -> set[str]:
    """Qué columnas de atribución (`created_at`, `origen`, `utm`) existen ya en
    `pichangol_reservas`. Mientras el SQL manual no se corra, el insert de
    reservas sigue igual que siempre (no se rompe la reserva por marketing)."""
    global _cols_reservas, _cols_leidas_en
    from db import pg
    if _cols_reservas is not None and time.time() - _cols_leidas_en < COLS_TTL_S:
        return _cols_reservas
    if not pg.habilitado:
        return set()
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'pichangol_reservas' "
                        "AND column_name IN ('created_at','origen','utm')")
            _cols_reservas = {r[0] for r in cur.fetchall()}
            _cols_leidas_en = time.time()
    except Exception:  # noqa: BLE001
        return _cols_reservas or set()
    return _cols_reservas


def _reiniciar() -> None:
    """Solo tests."""
    global _listo, _cols_reservas, _fallo_en, _cols_leidas_en
    _listo, _cols_reservas, _fallo_en, _cols_leidas_en = False, None, 0.0, 0.0
