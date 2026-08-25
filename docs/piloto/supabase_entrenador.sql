-- ============================================================
-- ENTRENADOR VIRTUAL · historial de análisis de técnica
-- El backend growth guarda aquí cada informe del coach IA; el APK
-- lee el historial device-first ("Mis análisis"). El video NO se
-- guarda en esta tabla (va al bucket canchas/entrenador/ y se poda).
-- Correr una vez en el SQL Editor de Supabase (DEV y PRD).
-- ============================================================

create table if not exists public.pichangol_entrenador_analisis (
  id       text primary key,
  email    text not null default '',
  deporte  text not null default 'tenis',
  golpe    text not null default '',
  informe  jsonb not null default '{}'::jsonb,
  creado   timestamptz not null default now()
);

create index if not exists idx_entrenador_email
  on public.pichangol_entrenador_analisis (email, creado desc);

alter table public.pichangol_entrenador_analisis enable row level security;

drop policy if exists entrenador_select on public.pichangol_entrenador_analisis;
create policy entrenador_select on public.pichangol_entrenador_analisis
  for select to anon, authenticated using (true);

drop policy if exists entrenador_insert on public.pichangol_entrenador_analisis;
create policy entrenador_insert on public.pichangol_entrenador_analisis
  for insert to anon, authenticated with check (true);
