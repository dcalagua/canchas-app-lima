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
--   · publicación de canal    → canales/<canalId>/<postId>.<ext>       (CanalesRepo.eliminarPost)
--   · canal eliminado         → canales/<canalId>/* (portada + posts)  (CanalesRepo.eliminarCanal)
--   · video del entrenador    → canchas/entrenador/<id>.mp4            (backend, tras el informe)
--   · "Dejar en virgen"       → todo lo anterior + verificacion/<usuario>/*
--
-- Y la torre (/admin → Mantenimiento → "Limpiar almacenamiento") barre lo que
-- el teléfono no alcanzó, incluyendo la media de chats/canales/grupos cuya
-- fila ya no existe.
--
-- PROTEGIDO (sin policy de delete = imborrable desde el app):
--   · canchas/recargas/*  — constancias de pago QR: registro contable/antifraude.
--   (ilustraciones/, afiches/ y bodega/packshot* sí tienen policy porque viven
--    en el mismo bucket, pero el barrido los trata como intocables por código.)
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

-- Bucket `chat`: avatares viejos + media de conversaciones ya borradas. Ojo:
-- mientras un mensaje siga existiendo, su foto/audio NO es huérfano y el
-- barrido no lo toca (la historia del chat se respeta, estilo WhatsApp).
drop policy if exists chat_bucket_delete_perfiles on storage.objects;
drop policy if exists chat_bucket_delete_limpieza on storage.objects;
create policy chat_bucket_delete_limpieza
  on storage.objects for delete
  to anon, authenticated
  using (bucket_id = 'chat');

-- Bucket `canales`: portada del canal y media de sus publicaciones
-- (`<canalId>/portada.jpg`, `<canalId>/<postId>.<ext>`).
drop policy if exists canales_bucket_delete_limpieza on storage.objects;
create policy canales_bucket_delete_limpieza
  on storage.objects for delete
  to anon, authenticated
  using (bucket_id = 'canales');

-- Bucket `grupos`: foto del grupo (`<grupoId>.jpg`).
drop policy if exists grupos_bucket_delete_limpieza on storage.objects;
create policy grupos_bucket_delete_limpieza
  on storage.objects for delete
  to anon, authenticated
  using (bucket_id = 'grupos');

-- Bucket `verificacion` (privado): doc + selfie. Minimización de datos
-- personales (Ley 29733): una vez validada la identidad, el documento no
-- debe quedarse para siempre. "Dejar en virgen" borra la carpeta propia.
drop policy if exists verificacion_bucket_delete_limpieza on storage.objects;
create policy verificacion_bucket_delete_limpieza
  on storage.objects for delete
  to anon, authenticated
  using (bucket_id = 'verificacion');
