-- Checks tipo WhatsApp (entregado / leído) por hilo y usuario.
-- Correr en QAS y luego en PROD. Requiere Realtime activado en la tabla.
create table if not exists public.pichangol_lecturas (
  hilo             text not null,
  email            text not null,
  entregado_hasta  timestamptz,
  leido_hasta      timestamptz,
  primary key (hilo, email)
);

-- Para que el remitente reciba en vivo el cambio de "entregado/leído":
-- Supabase Studio → Database → Replication → habilitar la tabla
-- public.pichangol_lecturas en la publicación supabase_realtime.
-- (o) alter publication supabase_realtime add table public.pichangol_lecturas;
