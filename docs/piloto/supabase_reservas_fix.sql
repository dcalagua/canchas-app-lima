-- =====================================================================
-- Pichangol · FIX reservas — garantiza esquema COMPLETO + RLS para que el
-- INSERT de una reserva NUNCA falle por columna faltante ni por RLS.
-- Correr en Supabase → SQL Editor. Idempotente (se puede correr varias veces).
--
-- Síntoma que arregla: el jugador reserva (le cobra Culqi) pero la reserva
-- queda "Pendiente de confirmar", el dueño no la ve y no llega notificación
-- → el INSERT a pichangol_reservas estaba fallando (columna faltante o RLS).
-- =====================================================================

-- 0) La tabla debe existir (si es proyecto nuevo, crea la base).
create table if not exists public.pichangol_reservas (
  id             text primary key,
  cancha_id      text not null,
  jugador        text not null default 'Jugador',
  fecha          text,
  dia            text not null default 'Hoy',
  hora_inicio    text not null default '',
  hora_fin       text not null default '',
  usuario        text not null default ''
);

-- 1) TODAS las columnas que manda la app (add if not exists = seguro repetir).
alter table public.pichangol_reservas
  add column if not exists jugador          text    not null default 'Jugador',
  add column if not exists nivel            text    not null default '',
  add column if not exists fecha            text,
  add column if not exists dia              text    not null default 'Hoy',
  add column if not exists hora_inicio      text    not null default '',
  add column if not exists hora_fin         text    not null default '',
  add column if not exists estado           text    not null default 'confirmada',
  add column if not exists traida_por_app   boolean not null default true,
  add column if not exists precio           numeric not null default 0,
  add column if not exists sena             integer not null default 0,
  add column if not exists pagado           boolean not null default false,
  add column if not exists usuario          text    not null default '',
  add column if not exists deporte          text    not null default '',
  add column if not exists moneda           text    not null default '',
  add column if not exists extras           jsonb   not null default '[]'::jsonb,
  add column if not exists telefono         text    not null default '',
  add column if not exists grupo_reserva_id text    not null default '';

-- 2) Anti-doble-reserva: un único slot por (cancha, fecha, hora de inicio).
--    Si falla por duplicados previos, límpialos y reintenta.
alter table public.pichangol_reservas
  drop constraint if exists uniq_slot_reserva;
alter table public.pichangol_reservas
  add  constraint uniq_slot_reserva unique (cancha_id, fecha, hora_inicio);

-- 3) RLS (piloto): el APK usa la anon key. Se PERMITE INSERT/SELECT/UPDATE/DELETE
--    a anon. Sin esta política, RLS bloquea el INSERT y la reserva nunca sube.
alter table public.pichangol_reservas enable row level security;
drop policy if exists reservas_pilot_all on public.pichangol_reservas;
create policy reservas_pilot_all on public.pichangol_reservas
  for all to anon, authenticated using (true) with check (true);

-- 4) Comprobación rápida (opcional): debe devolver la política creada.
-- select policyname, cmd, roles from pg_policies
--   where tablename = 'pichangol_reservas';
