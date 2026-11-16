-- OPERACIÓN DE LA ACADEMIA (asistencia, evaluación y bitácora de clases).
-- La web (backend/growth/web/anfitrion_academia_ops.py) y el APK
-- (lib/data/academia_ops_repo.dart) usan estas MISMAS tablas con los campos de
-- los modelos del app (Asistencia, EvaluacionAlumno, NotaClase). Para que el
-- APK pueda leerlas/escribirlas hay que correr DESPUÉS
-- `supabase_academia_operacion_rls.sql` (políticas + tabla de planes).
-- Sin estas tablas, las páginas web avisan y no rompen.
--
-- Correr a mano en Supabase: QAS ("Pichangol") y, con autorización, PCG-PRD.
-- Idempotente.

create table if not exists public.pichangol_academia_asistencias (
  academia_id text not null,
  alumno_id   text not null,
  dia         text not null,              -- 'YYYY-MM-DD' (Asistencia.claveDia)
  presente    boolean not null default true,
  avisado     boolean not null default false, -- ya se avisó a los padres ese día
  actualizado timestamptz not null default now(),
  primary key (alumno_id, dia)
);
create index if not exists pichangol_academia_asistencias_ac_dia
  on public.pichangol_academia_asistencias (academia_id, dia);

create table if not exists public.pichangol_academia_evaluaciones (
  academia_id text not null,
  alumno_id   text not null,
  plan_id     text not null,              -- 'plantilla_<deporte>' en la web
  habilidad   text not null,
  nivel       text not null check (nivel in ('inicial', 'enProceso', 'logrado')),
  ts          bigint not null,            -- ms epoch (EvaluacionAlumno.ts)
  primary key (alumno_id, plan_id, habilidad)
);
create index if not exists pichangol_academia_evaluaciones_ac
  on public.pichangol_academia_evaluaciones (academia_id, plan_id);

create table if not exists public.pichangol_academia_notas (
  id            text primary key,         -- 'nota_<µs>'
  academia_id   text not null,
  alumno_id     text not null,
  plan_id       text not null default '',
  sesion_numero int  not null default 0,  -- 0 = clase suelta
  fecha         text not null,            -- 'YYYY-MM-DD'
  desempeno     text not null check (desempeno in ('muyBien', 'bien', 'aReforzar')),
  nota          text not null default '',
  creado        timestamptz not null default now()
);
create index if not exists pichangol_academia_notas_al
  on public.pichangol_academia_notas (academia_id, alumno_id, creado desc);

-- RLS activado SIN políticas aquí = solo el backend (rol postgres). Las
-- políticas para el APK están en `supabase_academia_operacion_rls.sql`.
alter table public.pichangol_academia_asistencias enable row level security;
alter table public.pichangol_academia_evaluaciones enable row level security;
alter table public.pichangol_academia_notas enable row level security;
