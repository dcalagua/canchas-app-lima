-- ============================================================
-- MI BODEGA · Fase 2: PEDIDOS A LA CANCHA
-- El jugador pide desde su cancha/mesa (2 cervezas 🍺), al dueño le
-- llega push, confirma y se lo llevan; al entregar cobra como siempre
-- (efectivo/Yape, cero comisión) y la venta queda registrada con el
-- stock descontado. Correr una vez en el SQL Editor de Supabase.
-- ============================================================

-- 1) PEDIDOS (estado: pendiente | confirmado | entregado | rechazado |
--    cancelado). items = [{producto_id, nombre, cantidad, precio}].
create table if not exists public.pichangol_bodega_pedidos (
  id             text primary key,
  dueno          text not null default '',
  cliente        text not null default '',
  cliente_nombre text not null default '',
  zona           text not null default '',
  items          jsonb not null default '[]'::jsonb,
  total          numeric not null default 0,
  moneda         text not null default 'S/',
  estado         text not null default 'pendiente',
  creado         timestamptz not null default now(),
  actualizado    timestamptz not null default now()
);
create index if not exists idx_bodega_ped_dueno
  on public.pichangol_bodega_pedidos (dueno, creado desc);
create index if not exists idx_bodega_ped_cliente
  on public.pichangol_bodega_pedidos (cliente, creado desc);

-- 2) CONFIG de la bodega: el dueño decide si acepta pedidos y sus ZONAS
--    (a dónde llevar: Cancha 1, Cancha 2, Mesa…). Apagado por defecto.
create table if not exists public.pichangol_bodega_config (
  dueno          text primary key,
  acepta_pedidos boolean not null default false,
  zonas          jsonb not null default
    '["Cancha 1","Cancha 2","Mesa","Mostrador"]'::jsonb,
  updated_at     timestamptz not null default now()
);

-- 3) RLS permisiva (piloto, igual que el resto de tablas pichangol_*).
alter table public.pichangol_bodega_pedidos enable row level security;
alter table public.pichangol_bodega_config  enable row level security;

drop policy if exists bodega_ped_all on public.pichangol_bodega_pedidos;
create policy bodega_ped_all on public.pichangol_bodega_pedidos
  for all using (true) with check (true);

drop policy if exists bodega_cfg_all on public.pichangol_bodega_config;
create policy bodega_cfg_all on public.pichangol_bodega_config
  for all using (true) with check (true);
