-- REPORTE DE CANCELACIONES: registro histórico de reservas canceladas.
-- Corre esto en Supabase → SQL Editor (proyecto del piloto).
--
-- La cancelación BORRA la fila de pichangol_reservas (así el UNIQUE libera el
-- horario al instante); esta tabla guarda la COPIA para el reporte del dueño
-- (Reportes → Cancelaciones).

create table if not exists public.pichangol_reservas_canceladas (
  id            bigint generated always as identity primary key,
  reserva_id    text not null,
  cancha_id     text not null,
  cancha_nombre text not null default '',
  local         text not null default '',
  dueno         text not null default '',   -- correo del dueño (filtro del reporte)
  jugador       text not null default '',
  usuario       text not null default '',   -- correo del jugador
  fecha         text not null default '',   -- ISO "2026-08-19" (fecha reservada)
  hora_inicio   text not null default '',
  hora_fin      text not null default '',
  precio        numeric not null default 0,
  moneda        text not null default 'S/',
  pagado        boolean not null default false,
  sena          numeric not null default 0,  -- seña adelantada (queda a favor del dueño)
  medio_pago    text not null default '',
  cancelado_por text not null default '',   -- quién canceló
  cancelada_en  timestamptz not null default now()
);

-- Si ya habías creado la tabla sin `sena`, esto la agrega (idempotente).
alter table public.pichangol_reservas_canceladas
  add column if not exists sena numeric not null default 0;

create index if not exists idx_canceladas_dueno
  on public.pichangol_reservas_canceladas (dueno, cancelada_en desc);

-- RLS (piloto): el APK usa la anon key.
alter table public.pichangol_reservas_canceladas enable row level security;
drop policy if exists canceladas_pilot_all on public.pichangol_reservas_canceladas;
create policy canceladas_pilot_all on public.pichangol_reservas_canceladas
  for all to anon, authenticated using (true) with check (true);
