-- =====================================================================
-- Pichangol · Reseñas de canchas (⭐ + comentario)
-- Reemplaza el rating "presentacional" por reputación real. Una reseña por
-- (cancha, autor) → el jugador puede editar la suya (upsert).
-- Ejecutar en Supabase → SQL Editor. IDEMPOTENTE.
-- Multi-país: nada depende del país. RLS del piloto abierto a `anon` (el APK usa
-- la clave anónima); endurecer por auth en una fase posterior.
-- =====================================================================

create table if not exists public.pichangol_resenas (
  id           text        primary key,
  cancha_id    text        not null,
  autor_email  text        not null,
  autor_nombre text        not null default '',
  estrellas    int         not null check (estrellas between 1 and 5),
  comentario   text        not null default '',
  creado       timestamptz not null default now(),
  unique (cancha_id, autor_email)
);

create index if not exists idx_resenas_cancha
  on public.pichangol_resenas (cancha_id);

alter table public.pichangol_resenas enable row level security;

drop policy if exists resenas_lectura on public.pichangol_resenas;
create policy resenas_lectura
  on public.pichangol_resenas for select
  to anon, authenticated using (true);

drop policy if exists resenas_escritura on public.pichangol_resenas;
create policy resenas_escritura
  on public.pichangol_resenas for all
  to anon, authenticated using (true) with check (true);
