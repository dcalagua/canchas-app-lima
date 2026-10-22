-- ============================================================================
-- Pichangol · COSECHA de la PRIMERA FOTO de cada lugar (web, sep-2026)
-- ----------------------------------------------------------------------------
-- La web muestra siempre la primera foto (como el app). Resolverla cuesta una
-- consulta a Google por lugar; esta tabla la guarda para que se pague UNA vez
-- y no en cada visita ni en cada redeploy del backend.
--
-- Cumplimiento de los términos de Google Maps Platform: el place_id se puede
-- guardar sin límite; las URLs de foto son contenido cacheable por hasta
-- 30 días → el backend las REFRESCA sola cuando `actualizado` pasa de 30 días
-- (columna `actualizado`), nunca descarga el archivo.
--
-- Clave: `place_id` de Google para lugares descubiertos, o `cancha:<id>` para
-- una cancha registrada sin fotos propias. Corre en Supabase → SQL Editor del
-- proyecto Pichangol (QAS) y, con autorización, en PCG-PRD. Idempotente.
-- ============================================================================

create table if not exists public.pichangol_lugares_fotos (
  clave        text primary key,
  nombre       text not null default '',
  lat          double precision,
  lng          double precision,
  fotos        jsonb not null default '[]'::jsonb,
  actualizado  timestamptz not null default now()
);

create index if not exists idx_lugares_fotos_actualizado
  on public.pichangol_lugares_fotos (actualizado);

-- La escribe el BACKEND (Postgres directo, sin RLS). Para que el APK pueda
-- leerla más adelante, lectura al rol anon como el resto de tablas del piloto.
alter table public.pichangol_lugares_fotos enable row level security;

drop policy if exists lugares_fotos_select on public.pichangol_lugares_fotos;
create policy lugares_fotos_select on public.pichangol_lugares_fotos
  for select to anon, authenticated using (true);
