-- =====================================================================
-- Pichangol · Invitaciones de academia (invitar por correo / teléfono)
-- Ejecutar en Supabase → SQL Editor. Idempotente (se puede correr 2 veces).
--
-- El profe invita a un alumno por CORREO (le aparece sola al entrar a la app,
-- match por email) y/o por TELÉFONO (se entrega por WhatsApp con el código).
-- Cada fila = una invitación (columna `data` jsonb con la Invitacion completa).
-- `academia_id` y `email` van sueltos para filtrar rápido; `estado` para ver
-- pendientes/aceptadas. No se guarda DNI aquí (Ley 29733).
-- =====================================================================

create table if not exists public.pichangol_invitaciones (
  id          text primary key,
  academia_id text        not null,
  email       text,
  estado      text        not null default 'pendiente',
  data        jsonb       not null,
  updated_at  timestamptz not null default now()
);

-- Índices para las dos consultas del app: por academia (profe) y por email
-- (el alumno ve las suyas al entrar con su cuenta de Google).
create index if not exists idx_invitaciones_academia
  on public.pichangol_invitaciones (academia_id);
create index if not exists idx_invitaciones_email
  on public.pichangol_invitaciones (email);

-- --------------------------------------------------------------------
-- RLS: mismo criterio del piloto que `pichangol_matriculas` (el APK usa la
-- clave anónima). Lectura/escritura al rol anon. Endurecer por dueño/alumno
-- en una fase posterior (auth).
-- --------------------------------------------------------------------
alter table public.pichangol_invitaciones enable row level security;

drop policy if exists invitaciones_lectura on public.pichangol_invitaciones;
create policy invitaciones_lectura
  on public.pichangol_invitaciones for select
  to anon, authenticated
  using (true);

drop policy if exists invitaciones_insert on public.pichangol_invitaciones;
create policy invitaciones_insert
  on public.pichangol_invitaciones for insert
  to anon, authenticated
  with check (true);

drop policy if exists invitaciones_update on public.pichangol_invitaciones;
create policy invitaciones_update
  on public.pichangol_invitaciones for update
  to anon, authenticated
  using (true) with check (true);
