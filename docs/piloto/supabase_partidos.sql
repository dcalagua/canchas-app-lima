-- =====================================================================
-- Pichangol · Partidos abiertos ("busca con quién jugar" — el "Match")
-- Ejecutar en Supabase → SQL Editor. IDEMPOTENTE.
--
-- Cualquier jugador publica un partido con cupos; otros se apuntan. El ROSTER y
-- el chat de coordinación REUTILIZAN los grupos (pichangol_grupos +
-- pichangol_grupo_miembros) con el MISMO id del partido — corre antes el SQL de
-- grupos (docs/piloto/supabase_verificacion_grupos_chat.sql).
--
-- RLS del piloto: abierto a anon (el APK usa la clave anónima). Endurecer luego.
-- =====================================================================

create table if not exists public.pichangol_partidos (
  id            text        primary key,
  creador_email text        not null default '',
  creador_nombre text       not null default '',
  deporte       text        not null default 'futbol',
  titulo        text        not null default '',
  fecha         text        not null default '',   -- 'YYYY-MM-DD'
  hora          text        not null default '',   -- 'HH:mm'
  sede_nombre   text        not null default '',
  lat           double precision,
  lng           double precision,
  cupos         integer     not null default 10,
  nota          text        not null default '',
  creado        timestamptz not null default now()
);

create index if not exists idx_partidos_fecha
  on public.pichangol_partidos (fecha, hora);

alter table public.pichangol_partidos enable row level security;

-- Lectura para todos (descubrir partidos cercanos).
drop policy if exists partidos_lectura on public.pichangol_partidos;
create policy partidos_lectura
  on public.pichangol_partidos for select
  to anon, authenticated using (true);

-- Crear/editar/borrar: en el piloto abierto a anon (el creador administra el
-- suyo desde el APK). Endurecer por dueño con auth en una fase posterior.
drop policy if exists partidos_write on public.pichangol_partidos;
create policy partidos_write
  on public.pichangol_partidos for all
  to anon, authenticated using (true) with check (true);
