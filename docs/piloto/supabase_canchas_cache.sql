-- ============================================================================
-- Pichangol · COSECHA de canchas descubiertas (costo CERO con Google Places)
-- ----------------------------------------------------------------------------
-- La primera persona que explora una zona la descubre vía Google y la app
-- guarda aquí lo esencial (place_id, nombre, dirección, lat/lng, deporte).
-- Desde entonces TODOS leen de esta tabla: instantáneo, gratis y menos cuota.
-- NO se guardan fotos de Google (caducan + licencia): la lista usa placeholder.
--
-- Corre esto en Supabase → SQL Editor del proyecto Pichangol. Idempotente.
-- ============================================================================

create table if not exists public.pichangol_canchas_cache (
  id        text primary key,          -- place_id de Google (con prefijo gp_)
  nombre    text not null,
  direccion text,
  lat       double precision not null,
  lng       double precision not null,
  deporte   text not null,             -- futbol | tenis | padel | ...
  visto_en  timestamptz not null default now()
);

create index if not exists idx_canchas_cache_lat on public.pichangol_canchas_cache (lat);
create index if not exists idx_canchas_cache_lng on public.pichangol_canchas_cache (lng);

-- RLS permisivo del piloto (misma política que el resto de tablas pichangol_*).
alter table public.pichangol_canchas_cache enable row level security;

drop policy if exists canchas_cache_select on public.pichangol_canchas_cache;
create policy canchas_cache_select on public.pichangol_canchas_cache
  for select to anon, authenticated using (true);

drop policy if exists canchas_cache_insert on public.pichangol_canchas_cache;
create policy canchas_cache_insert on public.pichangol_canchas_cache
  for insert to anon, authenticated with check (true);

drop policy if exists canchas_cache_update on public.pichangol_canchas_cache;
create policy canchas_cache_update on public.pichangol_canchas_cache
  for update to anon, authenticated using (true) with check (true);
