-- ============================================================================
-- Pichangol · CACHÉ de consultas a Google Places en la Edge `places-cerca`
-- ----------------------------------------------------------------------------
-- Factura de Google de oct-2026 (USD 247, previsión USD 460/mes): casi todo
-- era "Places API Text Search Pro". Cada llamada a `places-cerca` hace ~18
-- Text Search (12 frases + páginas extra) ≈ USD 0.60, y el APK la llamaba en
-- cada apertura de Explorar en zonas con pocas canchas cosechadas.
--
-- Con esta tabla la Edge guarda la respuesta de cada zona consultada y la
-- reutiliza 30 días para cualquier punto a ≤ 3 km (APK nuevo, APK VIEJO y
-- web por igual). Las respuestas con fotos se reutilizan 1 día.
--
-- Sin políticas RLS: solo la Edge (service role) la lee y escribe.
-- Corre esto en Supabase → SQL Editor. Idempotente.
-- ============================================================================

create table if not exists public.pichangol_places_consultas (
  id         bigserial primary key,
  region     text not null,
  lat        double precision not null,
  lng        double precision not null,
  radio      double precision not null,
  fotos      boolean not null default false,
  places     jsonb not null default '[]'::jsonb,
  creado_en  timestamptz not null default now()
);

create index if not exists idx_places_consultas_zona
  on public.pichangol_places_consultas (region, lat, lng, creado_en desc);

alter table public.pichangol_places_consultas enable row level security;
