-- ============================================================
-- MI BODEGA · CUENTA ABIERTA ("apúntamelo, pago cuando me vaya")
-- El cliente identificado consume durante su estadía (pedidos a la
-- cancha o consumo en el mostrador) y todo se ANOTA en su cuenta; al
-- retirarse el dueño la cierra y cobra TODO junto (efectivo/Yape,
-- cero comisión) — recién ahí se registra UNA venta en el reporte.
-- El stock se descuenta al entregar cada consumo (eso no espera).
-- Correr una vez en el SQL Editor de Supabase.
-- ============================================================

-- 1) CUENTAS (estado: abierta | cerrada). Una abierta por cliente y
--    local. items = [{producto_id, nombre, cantidad, precio}].
create table if not exists public.pichangol_bodega_cuentas (
  id             text primary key,
  dueno          text not null default '',
  cliente        text not null default '',
  cliente_nombre text not null default '',
  items          jsonb not null default '[]'::jsonb,
  total          numeric not null default 0,
  moneda         text not null default 'S/',
  estado         text not null default 'abierta',
  medio_pago     text not null default '',
  creado         timestamptz not null default now(),
  actualizado    timestamptz not null default now(),
  cerrado        timestamptz
);
create index if not exists idx_bodega_cta_dueno
  on public.pichangol_bodega_cuentas (dueno, creado desc);
create index if not exists idx_bodega_cta_cliente
  on public.pichangol_bodega_cuentas (cliente, estado);

-- 2) CONFIG: el dueño decide si permite cuenta abierta y el TOPE por
--    cuenta (en su moneda; 0 = sin tope). Apagado por defecto.
alter table public.pichangol_bodega_config
  add column if not exists permite_cuenta boolean not null default false;
alter table public.pichangol_bodega_config
  add column if not exists tope_cuenta numeric not null default 100;

-- 3) RLS permisiva (piloto, igual que el resto de tablas pichangol_*).
alter table public.pichangol_bodega_cuentas enable row level security;

drop policy if exists bodega_cta_all on public.pichangol_bodega_cuentas;
create policy bodega_cta_all on public.pichangol_bodega_cuentas
  for all using (true) with check (true);
