-- ============================================================
-- MI BODEGA (POS ligero del dueño, función Pichangol Pro)
-- Catálogo con stock + registro de ventas de la bodega del local
-- (cerveza, gaseosas, agua, snacks…). La plata NO pasa por Pichangol:
-- el dueño cobra con su Yape/efectivo y aquí solo se REGISTRA la venta
-- y se descuenta el stock (control de logística + reportes).
-- Correr una vez en el SQL Editor de Supabase.
-- ============================================================

-- 1) PRODUCTOS de la bodega (por dueño; carta_id = id público de la carta
--    digital /b/{carta_id}, derivado del correo SIN exponerlo).
create table if not exists public.pichangol_bodega_productos (
  id         text primary key,
  dueno      text not null default '',
  carta_id   text not null default '',
  nombre     text not null default '',
  categoria  text not null default '',
  precio     numeric not null default 0,
  stock      integer not null default 0,
  stock_min  integer not null default 0,
  foto_url   text,
  moneda     text not null default 'S/',
  eliminado  boolean not null default false,
  updated_at timestamptz not null default now()
);
create index if not exists idx_bodega_prod_dueno
  on public.pichangol_bodega_productos (dueno);
create index if not exists idx_bodega_prod_carta
  on public.pichangol_bodega_productos (carta_id);

-- 2) VENTAS registradas en la caja rápida (items = [{producto_id, nombre,
--    cantidad, precio}]). medio_pago: efectivo | yape | cortesia.
create table if not exists public.pichangol_bodega_ventas (
  id         text primary key,
  dueno      text not null default '',
  items      jsonb not null default '[]'::jsonb,
  total      numeric not null default 0,
  medio_pago text not null default 'efectivo',
  creado     timestamptz not null default now()
);
create index if not exists idx_bodega_ventas_dueno
  on public.pichangol_bodega_ventas (dueno, creado desc);

-- 3) RLS permisiva (piloto, igual que el resto de tablas pichangol_*: la app
--    entra con la anon key y filtra por dueño).
alter table public.pichangol_bodega_productos enable row level security;
alter table public.pichangol_bodega_ventas    enable row level security;

drop policy if exists bodega_prod_all on public.pichangol_bodega_productos;
create policy bodega_prod_all on public.pichangol_bodega_productos
  for all using (true) with check (true);

drop policy if exists bodega_ventas_all on public.pichangol_bodega_ventas;
create policy bodega_ventas_all on public.pichangol_bodega_ventas
  for all using (true) with check (true);
