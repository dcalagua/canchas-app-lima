-- =====================================================================
-- Pichangol · Lista de espera de horarios (waitlist)
-- Cuando una hora está tomada, el jugador se anota; si se libera (una reserva
-- se cancela), el dueño ve quién espera y lo contacta — y el jugador ve
-- device-first que su hora quedó libre. Una entrada por (cancha, fecha, hora,
-- jugador) → idempotente (upsert).
-- Ejecutar en Supabase → SQL Editor. IDEMPOTENTE.
-- Multi-país: nada depende del país. RLS del piloto abierto a `anon` (el APK usa
-- la clave anónima); endurecer por auth en una fase posterior.
-- =====================================================================

create table if not exists public.pichangol_espera (
  id         text        primary key,
  cancha_id  text        not null,
  fecha      text        not null,           -- 'YYYY-MM-DD' (fecha REAL del slot)
  hora       text        not null,           -- 'HH:mm'
  usuario    text        not null,           -- correo del jugador que espera
  nombre     text        not null default '',
  telefono   text        not null default '',
  creado     timestamptz not null default now(),
  unique (cancha_id, fecha, hora, usuario)
);

create index if not exists idx_espera_slot
  on public.pichangol_espera (cancha_id, fecha, hora);

alter table public.pichangol_espera enable row level security;

drop policy if exists espera_lectura on public.pichangol_espera;
create policy espera_lectura
  on public.pichangol_espera for select
  to anon, authenticated using (true);

drop policy if exists espera_escritura on public.pichangol_espera;
create policy espera_escritura
  on public.pichangol_espera for all
  to anon, authenticated using (true) with check (true);
