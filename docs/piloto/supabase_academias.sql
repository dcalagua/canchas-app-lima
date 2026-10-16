-- =====================================================================
-- Pichangol · Academias en la nube (sobreviven a reinstalar el APK)
-- Ejecutar en Supabase → SQL Editor. Idempotente (se puede correr 2 veces).
--
-- Antes: las academias vivían solo en el celular (SharedPreferences) y se
-- perdían al desinstalar. Ahora se guardan aquí (columna `data` jsonb con la
-- academia completa) y el APK las vuelve a cargar al arrancar.
-- =====================================================================

create table if not exists public.pichangol_academias (
  id         text primary key,
  dueno      text,
  data       jsonb       not null,
  eliminada  boolean     not null default false,
  updated_at timestamptz not null default now()
);

-- Índice para listar rápido las no eliminadas.
create index if not exists idx_academias_activas
  on public.pichangol_academias (eliminada);

-- --------------------------------------------------------------------
-- RLS: el directorio de academias es PÚBLICO (cualquiera las ve para
-- matricularse). El APK usa la clave anónima, así que damos lectura y
-- escritura al rol anon (mismo criterio que `pichangol_canchas` en el
-- piloto). Endurecer con auth por dueño en una fase posterior.
-- --------------------------------------------------------------------
alter table public.pichangol_academias enable row level security;

drop policy if exists academias_lectura on public.pichangol_academias;
create policy academias_lectura
  on public.pichangol_academias for select
  to anon, authenticated
  using (true);

drop policy if exists academias_insert on public.pichangol_academias;
create policy academias_insert
  on public.pichangol_academias for insert
  to anon, authenticated
  with check (true);

drop policy if exists academias_update on public.pichangol_academias;
create policy academias_update
  on public.pichangol_academias for update
  to anon, authenticated
  using (true) with check (true);
