-- LECTURA DE storage.objects PARA EL SERVIDOR (arregla el "0 huérfanos" falso).
--
-- Síntoma: la torre (/admin → Mantenimiento → Limpiar almacenamiento) reporta
-- "Archivos vistos: 14 (canchas: 14)" aunque el dashboard muestre archivos en
-- chat, canales, estados y verificacion. El barrido cree que esos buckets están
-- vacíos y responde un tranquilizador "0 huérfanos".
--
-- Causa: `storage.objects` tiene RLS. El rol con el que se conecta el backend
-- (`postgres`, vía el pooler) NO es superusuario en Supabase, así que sólo ve
-- las filas que alguna policy de SELECT le permita. El bucket `canchas` tiene
-- policies antiguas que aplican a PUBLIC —por eso ve esas 14— mientras que las
-- de los demás buckets se crearon `to anon, authenticated`, roles que el
-- backend no usa. Resultado: ceguera parcial, silenciosa.
--
-- Arreglo: darle lectura explícita al rol del SERVIDOR. No se toca `anon` ni
-- `authenticated`, así que ningún cliente gana visibilidad: esto sólo habilita
-- al backend (y sólo METADATOS de archivos: nombre, bucket, fechas; el
-- contenido sigue protegido por las policies de cada bucket).
--
-- Es idempotente y no rompe nada si el rol ya veía todo.
--
-- Correr en el SQL Editor del proyecto DEV/QAS ("Pichangol").
-- En PRD (PCG-PRD) lo aplica Claude.

drop policy if exists storage_lectura_servidor on storage.objects;
create policy storage_lectura_servidor
  on storage.objects for select
  to postgres
  using (true);

-- ── VERIFICACIÓN ──────────────────────────────────────────────────────────
-- Debe listar TODOS los buckets con archivos (no sólo `canchas`):
--   select bucket_id, count(*) from storage.objects
--     group by bucket_id order by bucket_id;
--
-- Si tras correr esto la torre SIGUE viendo sólo `canchas`, entonces el rol del
-- backend no es `postgres`: mira en la torre la línea "Usuario BD: <rol>" y
-- repite el `create policy` cambiando `to postgres` por ese rol.
