-- ============================================================================
-- Pichangol · FIDELIDAD DEL LOCAL ("cada N reservas, una hora gratis o un
-- descuento", pedido del director, 28-sep-2026)
-- ----------------------------------------------------------------------------
-- El DUEÑO configura por LOCAL (se copia a todas las canchas del local, como
-- los servicios extra de ámbito local): meta de reservas, premio (hora gratis
-- o % de descuento), ventana de días que cuenta y si cuentan todas las
-- reservas pagadas o solo las pagadas en línea. El jugador ve su progreso en
-- la ficha (app y web) y, al llegar a la meta, el premio se aplica en el
-- checkout. Cada premio usado queda en `pichangol_fidelidad_canjes` con las
-- reservas que lo ganaron (así el ciclo vuelve a cero sin contador aparte).
--
-- Todo lo escribe el BACKEND (pg-backend, rol del servicio) salvo la columna
-- `fidelidad`, que el APK del dueño también escribe con la anon key (misma
-- política que el resto de columnas de configuración de la cancha).
-- Correr en QAS (Pichangol) y en PRD (PCG-PRD).
-- ============================================================================

alter table public.pichangol_canchas
  add column if not exists fidelidad jsonb;

comment on column public.pichangol_canchas.fidelidad is
  'Tarjeta de fidelidad del local: {activa, meta, premio: hora_gratis|descuento, descuentoPct, ventanaDias, aplica: todas|online}. Igual en todas las canchas del local.';

create table if not exists public.pichangol_fidelidad_canjes (
  id             text primary key,                 -- fc_<µs>
  email          text not null,                    -- jugador (correo de Google, minúsculas)
  local_key      text not null,                    -- "<dueño>|<club>" en minúsculas = identidad del local
  cancha_id      text not null,                    -- cancha donde se usó
  reserva_ref    text not null,                    -- grupo_reserva_id o id de la reserva premiada
  reserva_ids    jsonb not null default '[]'::jsonb,
  tipo           text not null,                    -- hora_gratis | descuento
  descuento      numeric(10,2) not null default 0, -- lo que dejó de pagar el jugador
  moneda         text not null default 'PEN',
  estado         text not null default 'reservado',-- reservado (hold) | usado | devuelto
  reservas_contadas jsonb not null default '[]'::jsonb, -- refs de las reservas que ganaron el premio
  canal          text not null default 'app',      -- app | web
  creado         timestamptz not null default now(),
  actualizado    timestamptz not null default now()
);

create index if not exists idx_fid_canjes_email_local on public.pichangol_fidelidad_canjes (email, local_key);
create index if not exists idx_fid_canjes_ref on public.pichangol_fidelidad_canjes (reserva_ref);

alter table public.pichangol_fidelidad_canjes enable row level security;
-- Sin políticas: solo el backend (rol postgres/servicio) lee y escribe.
