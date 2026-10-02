-- =====================================================================
-- Pichangol · Bonos de horas prepagadas (packs) por local
-- El dueño vende packs de horas ("10 horas por S/360"); el jugador los compra
-- con Culqi y descuenta 1 hora al reservar en ESE local. Caja adelantada +
-- fidelización. La contabilidad de la COMPRA reusa /pagos/venta (por recibir +
-- comisión); el canje NO cobra de nuevo.
-- Ejecutar en Supabase → SQL Editor. IDEMPOTENTE.
-- Multi-país: el precio va en la moneda del local (no se guarda el símbolo).
-- RLS del piloto abierto a `anon`; endurecer por auth en una fase posterior.
-- =====================================================================

-- Ofertas del dueño (los packs que publica para su local).
create table if not exists public.pichangol_bonos (
  id      text        primary key,
  dueno   text        not null,            -- correo del dueño
  club    text        not null,            -- nombre del local
  nombre  text        not null default '',
  horas   int         not null check (horas > 0),
  precio  numeric     not null check (precio >= 0),
  activo  boolean     not null default true,
  creado  timestamptz not null default now()
);

create index if not exists idx_bonos_club on public.pichangol_bonos (club);
create index if not exists idx_bonos_dueno on public.pichangol_bonos (dueno);

-- Créditos comprados por los jugadores (saldo = horas_total - horas_usadas).
create table if not exists public.pichangol_bonos_comprados (
  id               text        primary key,
  bono_id          text        not null default '',
  dueno            text        not null,
  club             text        not null,
  comprador        text        not null,   -- correo del jugador
  comprador_nombre text        not null default '',
  horas_total      int         not null check (horas_total > 0),
  horas_usadas     int         not null default 0,
  precio           numeric     not null default 0,
  venta_id         text        not null default '',  -- idempotencia del pago
  creado           timestamptz not null default now()
);

create index if not exists idx_bonoscomp_comprador
  on public.pichangol_bonos_comprados (comprador);
create index if not exists idx_bonoscomp_club
  on public.pichangol_bonos_comprados (club);

alter table public.pichangol_bonos enable row level security;
alter table public.pichangol_bonos_comprados enable row level security;

drop policy if exists bonos_lectura on public.pichangol_bonos;
create policy bonos_lectura on public.pichangol_bonos
  for select to anon, authenticated using (true);
drop policy if exists bonos_escritura on public.pichangol_bonos;
create policy bonos_escritura on public.pichangol_bonos
  for all to anon, authenticated using (true) with check (true);

drop policy if exists bonoscomp_lectura on public.pichangol_bonos_comprados;
create policy bonoscomp_lectura on public.pichangol_bonos_comprados
  for select to anon, authenticated using (true);
drop policy if exists bonoscomp_escritura on public.pichangol_bonos_comprados;
create policy bonoscomp_escritura on public.pichangol_bonos_comprados
  for all to anon, authenticated using (true) with check (true);
