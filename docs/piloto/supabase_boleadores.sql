-- ============================================================================
-- Pichangol · BOLEADORES (sparring por turno como servicio extra, sep-2026)
-- ----------------------------------------------------------------------------
-- Diseño: docs/diseno-boleadores.md. Un jugador con identidad verificada se
-- registra como boleador (categoría de la Liga Pichangol, tarifa por turno,
-- locales donde atiende, disponibilidad). El cliente lo contrata al reservar
-- (solo pago en línea); el boleador recibe push y ACEPTA o RECHAZA. Pichangol
-- descuenta una comisión fija por turno (S/ 2 · $ 0.50 · Bs 3) y el neto entra
-- a "por recibir" en la misma cola de liquidaciones que los dueños.
--
-- Todo lo escribe el BACKEND (pg-backend, Postgres directo con el rol del
-- servicio): el APK y la web llaman a /boleadores/*. Por eso RLS queda
-- activado SIN políticas para anon/authenticated (la anon key no lee ni
-- escribe estas tablas; el backend entra como postgres, dueño de la tabla).
--
-- Correr en Supabase → SQL Editor (QAS "Pichangol"; PRD solo con autorización
-- del director). Idempotente.
-- ============================================================================

create table if not exists public.pichangol_boleadores (
  email        text primary key,                 -- correo de Google en minúsculas
  deporte      text not null default 'tenis',    -- tenis | padel
  categoria    text not null default '',         -- 5P · 5A · 5B · 4ta · 3ra · 2da · 1ra
  tarifa       numeric(10,2) not null default 0, -- por turno, unidad mayor de `moneda`
  moneda       text not null default 'PEN',      -- ISO: PEN | USD | BOB (país de sus locales)
  activo       boolean not null default true,    -- false = pausado (por él o por la torre)
  data         jsonb not null default '{}'::jsonb, -- nombre, foto, celular, canchas[], locales[], disponibilidad, etiquetas, stats
  creado       timestamptz not null default now(),
  actualizado  timestamptz not null default now()
);

create index if not exists pichangol_boleadores_activo_idx
  on public.pichangol_boleadores (activo, deporte);

-- Solicitudes: una por reserva con boleador. Estados: pendiente → aceptada |
-- rechazada | vencida | cancelada (cliente) | cancelada_boleador | devuelta.
create table if not exists public.pichangol_boleador_solicitudes (
  id                 text primary key,             -- bs_<microsegundos>
  boleador_email     text not null,
  cliente_email      text not null default '',
  cliente_nombre     text not null default '',
  reserva_ref        text not null default '',     -- grupo_reserva_id o id de la reserva
  cancha_id          text not null default '',
  club               text not null default '',
  fecha              text not null default '',     -- AAAA-MM-DD (fecha real del primer turno)
  hora_inicio        text not null default '',     -- HH:MM
  hora_fin           text not null default '',     -- HH:MM (fin del último turno)
  turnos             integer not null default 1,
  monto_centimos     integer not null default 0,   -- tarifa × turnos (lo que pagó el cliente por el boleador)
  comision_centimos  integer not null default 0,   -- comisión fija × turnos
  moneda             text not null default 'PEN',
  estado             text not null default 'pendiente',
  canal              text not null default 'app',  -- app | web
  charge_id          text not null default '',     -- cargo de Culqi/pasarela (para devolver la parte)
  vence_en           timestamptz,                  -- plazo para aceptar
  respondido_en      timestamptz,
  creado             timestamptz not null default now(),
  data               jsonb not null default '{}'::jsonb -- devolucion {estado, refund_id, monto_centimos}, motivo, etc.
);

create index if not exists pichangol_boleador_solicitudes_boleador_idx
  on public.pichangol_boleador_solicitudes (boleador_email, estado, fecha);
create index if not exists pichangol_boleador_solicitudes_cliente_idx
  on public.pichangol_boleador_solicitudes (cliente_email, creado desc);
create index if not exists pichangol_boleador_solicitudes_reserva_idx
  on public.pichangol_boleador_solicitudes (reserva_ref);

-- El local puede no querer boleadores externos (tiene sus propios profesores).
alter table public.pichangol_canchas
  add column if not exists permite_boleadores boolean not null default true;

-- RLS activado sin políticas: solo el backend (rol postgres) las toca.
alter table public.pichangol_boleadores enable row level security;
alter table public.pichangol_boleador_solicitudes enable row level security;
