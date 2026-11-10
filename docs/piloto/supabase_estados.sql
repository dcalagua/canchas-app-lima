-- ESTADOS / HISTORIAS (tipo WhatsApp): publicaciones efímeras que duran 24 h.
-- Texto (sobre color) o foto (bucket `estados`). Solo se muestran a los
-- contactos/conocidos del autor (el filtro es del lado del app).
-- Correr en QAS y luego en PROD.

-- 1) Tabla de estados ---------------------------------------------------------
create table if not exists public.pichangol_estados (
  id           text primary key,
  autor_email  text not null,
  autor_nombre text default '',
  tipo         text not null default 'texto',   -- 'texto' | 'foto'
  texto        text default '',                  -- contenido o pie de foto
  foto_url     text default '',                  -- vacío si es de texto
  bg           bigint default 4279405694,        -- color de fondo (ARGB=0xFF128C7E) del texto
  creado_en    timestamptz default now()
);

create index if not exists ix_estados_creado    on public.pichangol_estados (creado_en desc);
create index if not exists ix_estados_autor      on public.pichangol_estados (autor_email);

-- Música opcional (preview 30 s de iTunes/Apple + carátula). Si ya creaste la
-- tabla antes, corre solo estos ALTER:
alter table public.pichangol_estados add column if not exists musica_titulo  text default '';
alter table public.pichangol_estados add column if not exists musica_artista text default '';
alter table public.pichangol_estados add column if not exists musica_preview text default '';
alter table public.pichangol_estados add column if not exists musica_art     text default '';

-- 2) Vistas: quién vio cada estado (para "visto por N") -----------------------
create table if not exists public.pichangol_estados_vistas (
  estado_id  text not null references public.pichangol_estados(id) on delete cascade,
  email      text not null,
  visto_en   timestamptz default now(),
  primary key (estado_id, email)
);

-- 3) Limpieza opcional de estados vencidos (correr a mano o por cron) ----------
--   delete from public.pichangol_estados where creado_en < now() - interval '24 hours';

-- 4) Bucket público para las fotos de estado ----------------------------------
--   En Supabase Studio → Storage → New bucket → nombre "estados" → Public.
--   (Mismo esquema que el bucket "productos".)
--
--   OJO: "Public" solo da LECTURA pública; para SUBIR falta la política de
--   escritura. Corre esto (igual que el bucket "productos"):
create policy "estados_leer"       on storage.objects
  for select to public using (bucket_id = 'estados');
create policy "estados_subir"      on storage.objects
  for insert to public with check (bucket_id = 'estados');
create policy "estados_actualizar" on storage.objects
  for update to public using (bucket_id = 'estados');
