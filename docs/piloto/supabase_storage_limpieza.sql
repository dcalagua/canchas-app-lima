-- LIMPIEZA DE STORAGE — políticas de DELETE por bucket.
-- Sin estas policies, el app NO puede borrar archivos (RLS bloquea el DELETE
-- en silencio) y los buckets acumulan huérfanos para siempre: fotos de
-- canchas eliminadas, historias vencidas, avatares viejos, productos
-- borrados, documentos de identidad ya validados.
--
-- El APK borra cada archivo cuando su dueño lógico muere:
--   · cancha eliminada        → canchas/<id>.jpg + canchas/<id>/*      (CanchasRepo.eliminar)
--   · estado borrado/vencido  → estados/<id>.jpg|.mp4                  (EstadosRepo.eliminar / limpiarVencidosDe)
--   · producto marketplace    → productos/<id>.jpg                     (ProductosRepo.eliminar)
--   · producto de bodega      → canchas/bodega/<id>.jpg                (BodegaRepo.eliminarProducto)
--   · campeonato eliminado    → canchas/campeonatos/<id>.jpg           (CampeonatosRepo.eliminar)
--   · avatar reemplazado      → chat/perfiles/<usuario>/* (viejos)     (PerfilesRepo.subirFoto)
--   · video del entrenador    → canchas/entrenador/<id>.mp4            (backend, tras el informe)
--   · "Dejar en virgen"       → todo lo anterior + verificacion/<usuario>/*
--
-- PROTEGIDO (sin policy de delete = imborrable desde el app):
--   · canchas/recargas/*  — constancias de pago QR: registro contable/antifraude.
--
-- Correr en el SQL Editor de Supabase (dev). En PRD lo aplica Claude (prd_10).

-- Bucket `canchas`: fotos de canchas, bodega, campeonatos, entrenador.
-- Se permite borrar TODO salvo las constancias de recargas.
drop policy if exists canchas_bucket_delete_limpieza on storage.objects;
create policy canchas_bucket_delete_limpieza
  on storage.objects for delete
  to anon, authenticated
  using (bucket_id = 'canchas' and name not like 'recargas/%');

-- Bucket `estados`: historias de 24 h — su media es desechable por diseño.
drop policy if exists estados_bucket_delete_limpieza on storage.objects;
create policy estados_bucket_delete_limpieza
  on storage.objects for delete
  to anon, authenticated
  using (bucket_id = 'estados');

-- Bucket `productos`: fotos del marketplace.
drop policy if exists productos_bucket_delete_limpieza on storage.objects;
create policy productos_bucket_delete_limpieza
  on storage.objects for delete
  to anon, authenticated
  using (bucket_id = 'productos');

-- Bucket `chat`: SOLO la carpeta de avatares (perfiles/). La media de los
-- chats es historia compartida (estilo WhatsApp) y NO se toca.
drop policy if exists chat_bucket_delete_perfiles on storage.objects;
create policy chat_bucket_delete_perfiles
  on storage.objects for delete
  to anon, authenticated
  using (bucket_id = 'chat' and name like 'perfiles/%');

-- Bucket `verificacion` (privado): doc + selfie. Minimización de datos
-- personales (Ley 29733): una vez validada la identidad, el documento no
-- debe quedarse para siempre. "Dejar en virgen" borra la carpeta propia.
drop policy if exists verificacion_bucket_delete_limpieza on storage.objects;
create policy verificacion_bucket_delete_limpieza
  on storage.objects for delete
  to anon, authenticated
  using (bucket_id = 'verificacion');
