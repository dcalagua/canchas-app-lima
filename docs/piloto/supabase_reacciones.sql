-- Reacciones (emoji) a un mensaje, tipo WhatsApp: UNA por persona por mensaje.
-- Correr en QAS y PROD. Requiere Realtime activado en la tabla.
create table if not exists public.pichangol_reacciones (
  mensaje_id text not null,
  email      text not null,
  emoji      text not null,
  hilo       text not null,
  creado     timestamptz default now(),
  primary key (mensaje_id, email)
);

create index if not exists ix_reacciones_hilo on public.pichangol_reacciones (hilo);

-- Realtime (para ver la reacción del otro en vivo):
-- Supabase Studio → Database → Replication → habilitar public.pichangol_reacciones
-- (o) alter publication supabase_realtime add table public.pichangol_reacciones;
