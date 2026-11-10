-- =====================================================================
-- Pichangol · Campeonatos de academias (llaves/tabla, inscripción)
-- Ejecutar en Supabase → SQL Editor. Idempotente (se puede correr 2 veces).
--
-- Cada fila = un campeonato completo (columna `data` jsonb con participantes,
-- fixture y resultados). Un solo upsert actualiza todo. Directorio público:
-- cualquiera ve llaves/tabla y se inscribe (motor de crecimiento del app).
-- =====================================================================

create table if not exists public.pichangol_campeonatos (
  id          text primary key,
  academia_id text        not null,
  dueno       text,
  data        jsonb       not null,
  eliminado   boolean     not null default false,
  updated_at  timestamptz not null default now()
);

create index if not exists idx_campeonatos_academia
  on public.pichangol_campeonatos (academia_id);

-- --------------------------------------------------------------------
-- RLS: mismo criterio del piloto que `pichangol_academias` (clave anónima).
-- Lectura/escritura al rol anon. Endurecer por dueño en una fase posterior.
-- --------------------------------------------------------------------
alter table public.pichangol_campeonatos enable row level security;

drop policy if exists campeonatos_lectura on public.pichangol_campeonatos;
create policy campeonatos_lectura
  on public.pichangol_campeonatos for select
  to anon, authenticated
  using (true);

drop policy if exists campeonatos_insert on public.pichangol_campeonatos;
create policy campeonatos_insert
  on public.pichangol_campeonatos for insert
  to anon, authenticated
  with check (true);

drop policy if exists campeonatos_update on public.pichangol_campeonatos;
create policy campeonatos_update
  on public.pichangol_campeonatos for update
  to anon, authenticated
  using (true) with check (true);
