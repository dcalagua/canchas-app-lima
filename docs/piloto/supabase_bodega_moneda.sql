-- MI BODEGA: moneda POR PAÍS del local ('S/', 'Bs', '$').
-- Complemento de supabase_bodega.sql (si ya lo corriste, corre solo esto).
alter table public.pichangol_bodega_productos
  add column if not exists moneda text not null default 'S/';
