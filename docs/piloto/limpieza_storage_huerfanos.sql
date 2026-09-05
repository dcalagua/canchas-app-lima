-- ⚠️ OBSOLETO — usa la TORRE DE CONTROL en su lugar.
--
-- Este script dependía de pg_net (asíncrono, sin forma de ver el error desde
-- el SQL Editor) y por eso podía "correr bien" sin borrar nada. El barrido
-- ahora vive en la torre: /admin → Mantenimiento → "Limpiar almacenamiento",
-- con revisión previa (cuántos huérfanos hay y ejemplos) antes de borrar.
-- Se conserva solo como referencia de las reglas de detección.
--
-- LIMPIEZA ÚNICA de archivos HUÉRFANOS históricos en Storage (dev/piloto).
-- Borra vía el STORAGE API (pg_net) — la forma correcta: elimina el archivo
-- físico, no solo la fila. Requiere haber corrido antes
-- supabase_storage_limpieza.sql (policies de DELETE por bucket).
--
-- QUÉ borra (solo lo huérfano, lo vivo NO se toca):
--   canchas   → fotos de canchas eliminadas/inexistentes (portada y galería),
--               clips del entrenador con >1 h (los vivos se borran solos),
--               fotos de productos de bodega eliminados (packshots NO),
--               afiches de campeonatos eliminados.
--   estados   → media de historias con más de 24 h (vencidas).
--   productos → fotos de productos del marketplace que ya no existen.
--   chat      → avatares viejos (queda solo el más reciente por usuario);
--               la media de los chats NO se toca.
--   verificacion → docs/selfies no referenciados por ninguna verificación.
--   PROTEGIDO → canchas/recargas/* e ilustraciones/ (no entran al barrido).
--
-- CÓMO correr (SQL Editor del proyecto):
--   1) Pega tu ANON KEY del proyecto en la línea marcada 👇 (Settings → API).
--   2) Corre TODO el script. Encola las eliminaciones (asíncronas).
--   3) Espera ~1 minuto y corre la VERIFICACIÓN del final: los contadores
--      deben bajar y no debe haber errores en net._http_response.

do $$
declare
  anon_key text := 'PEGA_AQUI_TU_ANON_KEY';  -- 👈 SOLO esto se edita
  base_url text;
  hdrs jsonb;
  r record;
  n int := 0;
begin
  if anon_key = 'PEGA_AQUI_TU_ANON_KEY' then
    raise exception 'Pega tu anon key en la línea marcada antes de correr.';
  end if;
  -- Storage API del proyecto dev (fijo; en PRD sería el ref de PCG-PRD).
  base_url := 'https://iuwnpjbxsltgmsybooeg.supabase.co/storage/v1/object';
  hdrs := jsonb_build_object(
    'Authorization', 'Bearer ' || anon_key,
    'apikey', anon_key);

  for r in (
    -- ── bucket CANCHAS ──
    select 'canchas' as bucket, o.name
    from storage.objects o
    where o.bucket_id = 'canchas' and (
      (o.name like 'entrenador/%' and o.created_at < now() - interval '1 hour')
      or (o.name like 'bodega/%' and o.name not like 'bodega/packshot%'
          and replace(replace(o.name, 'bodega/', ''), '.jpg', '') not in
              (select id::text from pichangol_bodega_productos
               where coalesce(eliminado, false) = false))
      or (o.name like 'campeonatos/%'
          and replace(replace(o.name, 'campeonatos/', ''), '.jpg', '') not in
              (select id::text from pichangol_campeonatos
               where coalesce(eliminado, false) = false))
      or (position('/' in o.name) = 0
          and replace(o.name, '.jpg', '') not in
              (select id::text from pichangol_canchas
               where coalesce(eliminada, false) = false))
      or (position('/' in o.name) > 0
          and split_part(o.name, '/', 1) not in
              ('entrenador', 'bodega', 'campeonatos', 'recargas', 'ilustraciones')
          and split_part(o.name, '/', 1) not in
              (select id::text from pichangol_canchas
               where coalesce(eliminada, false) = false))
    )
    union all
    -- ── bucket ESTADOS (historias vencidas) ──
    select 'estados', o.name
    from storage.objects o
    where o.bucket_id = 'estados'
      and regexp_replace(o.name, '\.(jpg|mp4)$', '') not in
          (select id::text from pichangol_estados
           where creado_en >= now() - interval '24 hours')
    union all
    -- ── bucket PRODUCTOS (marketplace) ──
    select 'productos', o.name
    from storage.objects o
    where o.bucket_id = 'productos'
      and replace(o.name, '.jpg', '') not in
          (select id::text from pichangol_productos)
    union all
    -- ── bucket CHAT: avatares viejos (queda el más nuevo por carpeta) ──
    select 'chat', o.name
    from storage.objects o
    where o.bucket_id = 'chat' and o.name like 'perfiles/%'
      and o.name <> (
        select max(o2.name) from storage.objects o2
        where o2.bucket_id = 'chat' and o2.name like 'perfiles/%'
          and split_part(o2.name, '/', 2) = split_part(o.name, '/', 2))
    union all
    -- ── bucket VERIFICACION: docs/selfies sin verificación que los referencie ──
    select 'verificacion', o.name
    from storage.objects o
    where o.bucket_id = 'verificacion'
      and o.name not in (
        select doc_path from pichangol_verificaciones where doc_path is not null
        union
        select selfie_path from pichangol_verificaciones
        where selfie_path is not null)
  ) loop
    perform net.http_delete(
      url := base_url || '/' || r.bucket || '/' || r.name,
      headers := hdrs);
    n := n + 1;
  end loop;
  raise notice 'Encoladas % eliminaciones vía Storage API (asíncronas).', n;
end $$;

-- ───────── VERIFICACIÓN (correr ~1 minuto después) ─────────
-- Cuántos archivos quedan por bucket (deben haber bajado):
-- select bucket_id, count(*) from storage.objects
--   group by bucket_id order by bucket_id;
-- Respuestas del Storage API con error (idealmente cero filas):
-- select status_code, count(*) from net._http_response
--   where status_code not in (200, 404) group by status_code;
