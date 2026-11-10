-- GRUPOS DE CHAT (tipo WhatsApp): foto del grupo + nombre editable + salir.
-- La tabla `pichangol_grupos` y `pichangol_grupo_miembros` ya existen (creación
-- del grupo). Esto agrega la FOTO del grupo, permite EDITAR (nombre/foto) y
-- SALIR (borrar mi membresía), más el bucket público `grupos` para las fotos.
-- Correr en QAS y luego en PROD.

-- 1) Columna de foto del grupo ------------------------------------------------
alter table public.pichangol_grupos
  add column if not exists foto_url text default '';

-- 2) Políticas RLS: permitir UPDATE del grupo y DELETE de miembros ------------
--   (mismo criterio permisivo que el resto del piloto; el control fino de quién
--   puede editar/salir lo hace el app). Si RLS está OFF en estas tablas, puedes
--   saltarte este bloque.
do $$ begin
  if not exists (select 1 from pg_policies
                 where tablename = 'pichangol_grupos' and policyname = 'grupos_update') then
    create policy "grupos_update" on public.pichangol_grupos
      for update to public using (true) with check (true);
  end if;
  if not exists (select 1 from pg_policies
                 where tablename = 'pichangol_grupo_miembros' and policyname = 'grupo_miembros_delete') then
    create policy "grupo_miembros_delete" on public.pichangol_grupo_miembros
      for delete to public using (true);
  end if;
end $$;

-- 3) Bucket público `grupos` para las fotos de grupo --------------------------
--   En Supabase Studio → Storage → New bucket → nombre "grupos" → Public.
--   Luego las políticas de escritura (leer/subir/actualizar), igual que "estados".
--   Idempotente: si ya existen, no falla (útil para re-correr el script).
do $$ begin
  if not exists (select 1 from pg_policies
                 where schemaname='storage' and tablename='objects' and policyname='grupos_leer') then
    create policy "grupos_leer" on storage.objects
      for select to public using (bucket_id = 'grupos');
  end if;
  if not exists (select 1 from pg_policies
                 where schemaname='storage' and tablename='objects' and policyname='grupos_subir') then
    create policy "grupos_subir" on storage.objects
      for insert to public with check (bucket_id = 'grupos');
  end if;
  if not exists (select 1 from pg_policies
                 where schemaname='storage' and tablename='objects' and policyname='grupos_actualizar') then
    create policy "grupos_actualizar" on storage.objects
      for update to public using (bucket_id = 'grupos');
  end if;
end $$;
