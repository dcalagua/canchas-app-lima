-- MÚSICA EN HISTORIAS · FASE 2: recorte (desde qué segundo suena) + enlace
-- EXACTO a la canción en Apple Music. Dos columnas nuevas en pichangol_estados.
-- Idempotente. Correr en QAS y luego en PROD.

alter table public.pichangol_estados
  add column if not exists musica_inicio_ms integer default 0;

alter table public.pichangol_estados
  add column if not exists musica_track_url text default '';
