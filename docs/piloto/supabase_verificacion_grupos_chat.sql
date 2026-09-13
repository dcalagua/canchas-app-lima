-- =====================================================================
-- Pichangol · Verificación de jugador + Chat generalizado + Grupos + Buckets
-- Ejecutar en Supabase → SQL Editor. IDEMPOTENTE (se puede correr varias veces).
-- Multi-país: nada aquí depende del país (la verificación es igual en PE/BO/EC).
-- RLS del piloto: el APK usa la clave anónima → se abre a `anon`. Endurecer por
-- auth en una fase posterior. Los documentos personales (Ley 29733) van a un
-- bucket PRIVADO y NUNCA se leen desde el app.
-- =====================================================================


-- =====================================================================
-- 1) VERIFICACIÓN DE JUGADOR  (tabla pichangol_verificaciones)
--    email = PK (el app hace upsert por email). doc/selfie = rutas en el
--    bucket privado `verificacion`. estado: 'no' | 'en_revision' | 'verificado'.
-- =====================================================================
create table if not exists public.pichangol_verificaciones (
  email       text        primary key,
  nombre      text        not null default '',
  doc_path    text        not null default '',
  selfie_path text        not null default '',
  estado      text        not null default 'verificado',
  creado      timestamptz not null default now()
);

alter table public.pichangol_verificaciones enable row level security;

drop policy if exists verif_lectura on public.pichangol_verificaciones;
create policy verif_lectura
  on public.pichangol_verificaciones for select
  to anon, authenticated using (true);

drop policy if exists verif_upsert on public.pichangol_verificaciones;
create policy verif_upsert
  on public.pichangol_verificaciones for all
  to anon, authenticated using (true) with check (true);


-- =====================================================================
-- 2) CHAT GENERALIZADO  (amplía pichangol_mensajes: cancha/grupo + fotos)
--    Si la tabla ya existe (chat de academia), solo se AGREGAN columnas y se
--    hace academia_id nullable. Si es proyecto nuevo, se crea completa.
-- =====================================================================
create table if not exists public.pichangol_mensajes (
  id           text        primary key,
  hilo         text        not null,
  tipo         text        not null default 'academia', -- academia | cancha | grupo
  ref_id       text        not null default '',         -- academiaId | canchaId | grupoId
  academia_id  text,                                     -- solo academia (nullable)
  cuenta_email text        not null default '',
  autor_email  text        not null default '',
  autor_nombre text        not null default '',
  es_profe     boolean     not null default false,
  texto        text        not null default '',
  media_url    text        not null default '',          -- foto adjunta ('' = solo texto)
  creado       timestamptz not null default now()
);

-- Columnas nuevas para instalaciones que ya tenían la tabla del chat de academia.
alter table public.pichangol_mensajes
  add column if not exists tipo      text not null default 'academia';
alter table public.pichangol_mensajes
  add column if not exists ref_id    text not null default '';
alter table public.pichangol_mensajes
  add column if not exists media_url text not null default '';

-- Los mensajes de cancha/grupo NO traen academia_id: hazlo nullable.
alter table public.pichangol_mensajes alter column academia_id drop not null;

create index if not exists idx_mensajes_hilo
  on public.pichangol_mensajes (hilo, creado);
create index if not exists idx_mensajes_ref
  on public.pichangol_mensajes (tipo, ref_id, creado);

-- Realtime (idempotente).
do $$
begin
  begin
    alter publication supabase_realtime add table public.pichangol_mensajes;
  exception when duplicate_object then null;
  end;
end $$;

alter table public.pichangol_mensajes enable row level security;

drop policy if exists mensajes_lectura on public.pichangol_mensajes;
create policy mensajes_lectura
  on public.pichangol_mensajes for select
  to anon, authenticated using (true);

drop policy if exists mensajes_insert on public.pichangol_mensajes;
create policy mensajes_insert
  on public.pichangol_mensajes for insert
  to anon, authenticated with check (true);


-- =====================================================================
-- 3) GRUPOS DE CHAT  (pichangol_grupos + pichangol_grupo_miembros)
--    Los mensajes del grupo viven en pichangol_mensajes (tipo='grupo').
-- =====================================================================
create table if not exists public.pichangol_grupos (
  id            text        primary key,
  nombre        text        not null default '',
  creador_email text        not null default '',
  creado        timestamptz not null default now()
);

create table if not exists public.pichangol_grupo_miembros (
  grupo_id text not null,
  email    text not null,
  nombre   text not null default '',
  primary key (grupo_id, email)
);

create index if not exists idx_grupo_miembros_email
  on public.pichangol_grupo_miembros (email);

alter table public.pichangol_grupos          enable row level security;
alter table public.pichangol_grupo_miembros  enable row level security;

drop policy if exists grupos_all on public.pichangol_grupos;
create policy grupos_all
  on public.pichangol_grupos for all
  to anon, authenticated using (true) with check (true);

drop policy if exists grupo_miembros_all on public.pichangol_grupo_miembros;
create policy grupo_miembros_all
  on public.pichangol_grupo_miembros for all
  to anon, authenticated using (true) with check (true);


-- =====================================================================
-- 4) BUCKETS DE STORAGE
--    `verificacion` → PRIVADO (documentos, Ley 29733): solo subir, no leer.
--    `chat`         → PÚBLICO (fotos del chat): subir + leer (getPublicUrl).
-- =====================================================================
insert into storage.buckets (id, name, public)
  values ('verificacion', 'verificacion', false)
  on conflict (id) do nothing;

insert into storage.buckets (id, name, public)
  values ('chat', 'chat', true)
  on conflict (id) do nothing;

-- verificacion: el APK (anon) SOLO sube. Nadie lee desde el app (privado).
drop policy if exists verif_bucket_insert on storage.objects;
create policy verif_bucket_insert
  on storage.objects for insert
  to anon, authenticated
  with check (bucket_id = 'verificacion');

-- chat: subir y leer (bucket público, para mostrar la foto en el chat).
drop policy if exists chat_bucket_insert on storage.objects;
create policy chat_bucket_insert
  on storage.objects for insert
  to anon, authenticated
  with check (bucket_id = 'chat');

drop policy if exists chat_bucket_select on storage.objects;
create policy chat_bucket_select
  on storage.objects for select
  to anon, authenticated
  using (bucket_id = 'chat');

-- =====================================================================
-- LISTO. Después de correr esto:
--   • La verificación de jugador ya guarda de verdad (tabla + bucket privado).
--   • El chat soporta cancha/grupo y fotos.
--   • Recuerda tener desplegada la Edge Function `push-mensaje` (rama grupo)
--     y el webhook/trigger de INSERT en pichangol_mensajes (ver
--     docs/piloto/supabase_mensajes.sql y docs/piloto/push_fcm_setup.md).
-- =====================================================================
