-- =====================================================================
-- Pichangol · Perfiles públicos de usuario
-- Ejecutar en Supabase → SQL Editor. Idempotente.
--
-- El nombre y la foto que la persona quiere mostrar (su Gmail a veces muestra
-- cualquier cosa). El chat lo usa para pintar nombre + foto en vez del correo.
-- Clave = email. El APK (clave anónima) hace upsert de SU propio perfil y lee
-- los de otros para mostrarlos.
-- =====================================================================

create table if not exists public.pichangol_perfiles (
  email       text        primary key,
  nombre      text        not null default '',
  foto_url    text,
  actualizado timestamptz not null default now()
);

alter table public.pichangol_perfiles enable row level security;

-- Lectura e inserción/actualización al rol anónimo (mismo criterio del piloto).
-- Endurecer por dueño del correo en una fase posterior (auth).
drop policy if exists perfiles_lectura on public.pichangol_perfiles;
create policy perfiles_lectura
  on public.pichangol_perfiles for select
  to anon, authenticated
  using (true);

drop policy if exists perfiles_upsert on public.pichangol_perfiles;
create policy perfiles_upsert
  on public.pichangol_perfiles for all
  to anon, authenticated
  using (true) with check (true);
