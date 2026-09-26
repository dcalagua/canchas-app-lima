-- =====================================================================
-- Pichangol · Matrículas en la nube ("Unirme con código")
-- Ejecutar en Supabase → SQL Editor. Idempotente (se puede correr 2 veces).
--
-- Permite que un alumno se una a una academia con su CÓDIGO desde su propio
-- celular y que el PROFE lo vea en el suyo. Cada fila = un alumno matriculado
-- (columna `data` jsonb con el Alumno completo). `academia_id` y `email` van
-- sueltos para filtrar rápido.
-- =====================================================================

create table if not exists public.pichangol_matriculas (
  id          text primary key,
  academia_id text        not null,
  email       text,
  data        jsonb       not null,
  eliminada   boolean     not null default false,
  updated_at  timestamptz not null default now()
);

-- Índices para las dos consultas del app: por academia (profe) y por email (alumno).
create index if not exists idx_matriculas_academia
  on public.pichangol_matriculas (academia_id);
create index if not exists idx_matriculas_email
  on public.pichangol_matriculas (email);

-- --------------------------------------------------------------------
-- RLS: mismo criterio del piloto que `pichangol_academias` (el APK usa la
-- clave anónima). Lectura/escritura al rol anon. Endurecer por dueño/alumno
-- en una fase posterior (auth). No se guarda DNI aquí (Ley 29733).
-- --------------------------------------------------------------------
alter table public.pichangol_matriculas enable row level security;

drop policy if exists matriculas_lectura on public.pichangol_matriculas;
create policy matriculas_lectura
  on public.pichangol_matriculas for select
  to anon, authenticated
  using (true);

drop policy if exists matriculas_insert on public.pichangol_matriculas;
create policy matriculas_insert
  on public.pichangol_matriculas for insert
  to anon, authenticated
  with check (true);

drop policy if exists matriculas_update on public.pichangol_matriculas;
create policy matriculas_update
  on public.pichangol_matriculas for update
  to anon, authenticated
  using (true) with check (true);
