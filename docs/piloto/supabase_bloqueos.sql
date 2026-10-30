-- =====================================================================
-- Pichangol · Horarios bloqueados por el dueño (no reservables)
-- Ejecutar en Supabase → SQL Editor. IDEMPOTENTE.
--
-- El dueño cierra un horario (mantenimiento, walk-in que tomó la cancha, etc.)
-- y ese slot deja de poder reservarse. Clave: (cancha_id, fecha, hora).
-- RLS del piloto: abierto a anon (el APK usa la clave anónima).
-- =====================================================================

create table if not exists public.pichangol_bloqueos (
  cancha_id text        not null,
  fecha     text        not null,  -- 'YYYY-MM-DD'
  hora      text        not null,  -- 'HH:mm'
  creado    timestamptz not null default now(),
  primary key (cancha_id, fecha, hora)
);

alter table public.pichangol_bloqueos enable row level security;

-- Lectura para todos (el jugador ve que el slot no está disponible).
drop policy if exists bloqueos_lectura on public.pichangol_bloqueos;
create policy bloqueos_lectura
  on public.pichangol_bloqueos for select
  to anon, authenticated using (true);

-- Bloquear/desbloquear: en el piloto abierto a anon (el dueño lo hace desde el
-- APK). Endurecer por dueño con auth en una fase posterior.
drop policy if exists bloqueos_write on public.pichangol_bloqueos;
create policy bloqueos_write
  on public.pichangol_bloqueos for all
  to anon, authenticated using (true) with check (true);
