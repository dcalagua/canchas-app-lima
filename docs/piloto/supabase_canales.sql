-- CANALES de difusión (tipo WhatsApp Channels): el dueño publica novedades y los
-- seguidores las ven (uno-a-muchos). Tablas del canal, seguidores y
-- publicaciones + bucket público `canales`. Las reacciones reutilizan la tabla
-- `pichangol_reacciones` (hilo = 'canal_<id>'). Correr en QAS y luego en PROD.

-- 1) Canal ---------------------------------------------------------------------
create table if not exists public.pichangol_canales (
  id           text primary key,
  nombre       text not null,
  descripcion  text default '',
  foto_url     text default '',
  owner_email  text not null,
  creado       timestamptz default now()
);
create index if not exists ix_canales_owner  on public.pichangol_canales (owner_email);
create index if not exists ix_canales_creado on public.pichangol_canales (creado desc);

-- 2) Seguidores ----------------------------------------------------------------
create table if not exists public.pichangol_canal_seguidores (
  canal_id  text not null references public.pichangol_canales(id) on delete cascade,
  email     text not null,
  desde     timestamptz default now(),
  primary key (canal_id, email)
);
create index if not exists ix_canal_seg_email on public.pichangol_canal_seguidores (email);

-- 3) Publicaciones -------------------------------------------------------------
create table if not exists public.pichangol_canal_posts (
  id           text primary key,
  canal_id     text not null references public.pichangol_canales(id) on delete cascade,
  autor_email  text not null,
  autor_nombre text default '',
  tipo         text not null default 'texto',   -- 'texto' | 'foto' | 'video'
  texto        text default '',
  media_url    text default '',
  creado       timestamptz default now()
);
create index if not exists ix_canal_posts on public.pichangol_canal_posts (canal_id, creado desc);

-- 4) Políticas RLS (permisivas, criterio del piloto; el control fino lo hace el
--    app: solo el dueño publica/edita). Si RLS está OFF, puedes saltar esto.
do $$
declare t text;
begin
  foreach t in array array[
    'pichangol_canales','pichangol_canal_seguidores','pichangol_canal_posts'
  ] loop
    execute format('alter table public.%I enable row level security;', t);
    if not exists (select 1 from pg_policies where tablename = t and policyname = t||'_all') then
      execute format(
        'create policy "%1$s_all" on public.%1$s for all to public using (true) with check (true);', t);
    end if;
  end loop;
end $$;

-- 5) Bucket público `canales` para fotos de canal y media de publicaciones ------
--   En Supabase Studio → Storage → New bucket → nombre "canales" → Public.
--   Políticas de escritura (idempotentes):
do $$ begin
  if not exists (select 1 from pg_policies
                 where schemaname='storage' and tablename='objects' and policyname='canales_leer') then
    create policy "canales_leer" on storage.objects
      for select to public using (bucket_id = 'canales');
  end if;
  if not exists (select 1 from pg_policies
                 where schemaname='storage' and tablename='objects' and policyname='canales_subir') then
    create policy "canales_subir" on storage.objects
      for insert to public with check (bucket_id = 'canales');
  end if;
  if not exists (select 1 from pg_policies
                 where schemaname='storage' and tablename='objects' and policyname='canales_actualizar') then
    create policy "canales_actualizar" on storage.objects
      for update to public using (bucket_id = 'canales');
  end if;
end $$;
