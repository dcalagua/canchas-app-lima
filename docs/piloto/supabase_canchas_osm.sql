-- ============================================================================
-- Pichangol · Canchas de OpenStreetMap (COMPLEMENTO permanente de Google)
-- ----------------------------------------------------------------------------
-- Pedido del director (oct-2026): "siembra OSM solo con nombre … bajar costo
-- lo máximo que se pueda SIN QUE AFECTE LO ACTUAL". Google Places sigue siendo
-- la fuente principal (a OSM le faltan 27-41 % de los locales comerciales);
-- OSM suma canchas CON NOMBRE que Google no trajo, sin costo por consulta.
--
-- Licencia ODbL: se puede guardar para siempre, con atribución
-- "© colaboradores de OpenStreetMap" (https://www.openstreetmap.org/copyright).
--
-- La llena el backend growth al arrancar (`web/osm.py::sembrar`) desde
-- `backend/growth/web/osm_canchas.json.gz`, solo si la tabla está vacía o el
-- archivo cambió. La Edge `places-cerca` la lee SOLO cuando la request trae
-- `osm=1` (APK nuevo); los APK viejos no reciben filas OSM.
--
-- RLS: lectura pública (datos abiertos), escritura solo service role /
-- postgres (el backend). Idempotente: se puede correr varias veces.
-- Corre esto en Supabase → SQL Editor (QAS; PRD solo con autorización).
-- ============================================================================

create table if not exists public.pichangol_canchas_osm (
  id             text primary key,          -- 'osm_' + n123 | w456 | r789
  nombre         text not null,
  deporte        text not null,             -- clave Pichangol (futbol, tenis, padel…)
  lat            double precision not null,
  lng            double precision not null,
  ciudad         text not null default '',
  pais           text not null default 'PE',
  leisure        text not null default '',  -- pitch | sports_centre
  actualizado_en timestamptz not null default now()
);

create index if not exists idx_canchas_osm_lat_lng
  on public.pichangol_canchas_osm (lat, lng);

alter table public.pichangol_canchas_osm enable row level security;

drop policy if exists canchas_osm_lectura on public.pichangol_canchas_osm;
create policy canchas_osm_lectura on public.pichangol_canchas_osm
  for select to anon, authenticated using (true);

-- Sin políticas de INSERT/UPDATE/DELETE: anon y authenticated no escriben.
revoke insert, update, delete, truncate on public.pichangol_canchas_osm from anon, authenticated;
grant select on public.pichangol_canchas_osm to anon, authenticated;
