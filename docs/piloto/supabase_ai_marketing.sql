-- ════════════════════════════════════════════════════════════════════════════
-- PICHANGOL AI MARKETING AGENT — tablas del agente + columnas de atribución.
-- Correr en QAS (Supabase "Pichangol") y, SOLO con la orden "pasa a PRD",
-- en PCG-PRD. Idempotente: se puede repetir sin efectos.
--
-- Las tablas ai_* tienen RLS ACTIVADO y SIN políticas: solo el backend
-- growth (DATABASE_URL) las lee/escribe; la anon key del APK no las ve.
-- El backend también las crea al arrancar (marketing/agente_ia/esquema.py);
-- este script existe para auditoría y para correrlo antes del deploy.
-- ════════════════════════════════════════════════════════════════════════════

-- 1) Campañas: agrupan contenidos con un objetivo y un KPI medible.
create table if not exists ai_marketing_campaigns (
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
);

-- 2) Decisión diaria del estratega (el "¿por qué publicamos esto?").
create table if not exists ai_marketing_strategy (
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
);

-- 3) Contenido generado (estados del flujo de aprobación).
create table if not exists ai_content (
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
  media_origen text check (media_origen in ('foto_real','foto_dueno','diseno','ia_conceptual')),
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
);
-- PUBLISHING = reclamada por el publicador mientras habla con la red social
-- (evita publicar dos veces). drop+add: re-correr el script actualiza la regla.
alter table ai_content drop constraint if exists ai_content_status_check;
alter table ai_content add constraint ai_content_status_check check (status in
  ('DRAFT','PENDING_APPROVAL','APPROVED','PUBLISHING','PUBLISHED','REJECTED','FAILED','CANCELLED'));
create index if not exists idx_ai_content_status on ai_content (status, scheduled_at);
create index if not exists idx_ai_content_creado on ai_content (created_at desc);

-- 4) Canchas REALES asociadas a cada contenido (evidencia o destacadas).
create table if not exists ai_content_targets (
  content_id text not null references ai_content(id) on delete cascade,
  cancha_id text not null,
  rol text not null default 'evidencia' check (rol in ('evidencia','destacada')),
  primary key (content_id, cancha_id)
);

-- 5) Clics del short-link (atribución).
create table if not exists ai_content_clicks (
  id bigserial primary key,
  content_id text not null references ai_content(id) on delete cascade,
  visitante text,                              -- hash anónimo (sin IP ni PII)
  creado timestamptz not null default now()
);
create index if not exists idx_ai_clicks_content on ai_content_clicks (content_id, creado);

-- 6) Métricas por ventana de medición.
create table if not exists ai_content_performance (
  content_id text not null references ai_content(id) on delete cascade,
  ventana text not null check (ventana in ('1h','24h','72h','7d','28d')),
  alcance int, impresiones int, interacciones int, reacciones int,
  comentarios int, compartidos int, clics int, reproducciones int,
  clics_link int, reservas_atribuidas int, ingresos_atribuidos numeric,
  engagement_rate numeric,
  raw jsonb not null default '{}'::jsonb,
  medido_en timestamptz not null default now(),
  primary key (content_id, ventana)
);

-- 7) Aprendizajes (alimentan al estratega).
create table if not exists ai_insights (
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
);
create index if not exists idx_ai_insights_vigente on ai_insights (vigente);

-- 8) Bitácora de todos los agentes.
create table if not exists ai_agent_logs (
  id bigserial primary key,
  agente text not null,
  accion text not null,
  content_id text,
  strategy_id text,
  nivel text not null default 'info' check (nivel in ('info','warn','error')),
  detalle jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists idx_ai_logs_creado on ai_agent_logs (created_at desc);

alter table ai_marketing_campaigns enable row level security;
alter table ai_marketing_strategy  enable row level security;
alter table ai_content             enable row level security;
alter table ai_content_targets     enable row level security;
alter table ai_content_clicks      enable row level security;
alter table ai_content_performance enable row level security;
alter table ai_insights            enable row level security;
alter table ai_agent_logs          enable row level security;

-- 9) Atribución en reservas (aditivo). Las filas viejas quedan con NULL
--    (no se les inventa fecha de creación); las nuevas reciben now().
alter table pichangol_reservas add column if not exists created_at timestamptz;
alter table pichangol_reservas alter column created_at set default now();
alter table pichangol_reservas add column if not exists origen text;   -- 'web' | 'app' | 'admin' | null
alter table pichangol_reservas add column if not exists utm jsonb;     -- {"content":"<codigo>","source":"facebook",...}
create index if not exists idx_reservas_utm_content on pichangol_reservas ((utm->>'content'));
