-- ============================================================================
-- Pichangol · Borrar la ACADEMIA DEMO ("Jartur · Country Club El Bosque")
-- ----------------------------------------------------------------------------
-- Síntoma que resuelve: reinstalas el APK y siempre reaparece la academia
-- "Academia de Tenis J. Arthur Baldeón" (Country Club El Bosque), aunque hayas
-- dejado la app en virgen. Causa: era la academia DEMO que la app sembraba sola
-- en dev; si además quedó guardada en Supabase, se re-baja de la nube en cada
-- instalación limpia. En el build nuevo ya NO se auto-siembra; esto elimina la
-- copia que pudiera haber quedado en la nube.
--
-- Corre esto en Supabase → SQL Editor del proyecto de Pichangol. Idempotente.
-- ============================================================================

-- Borrado DURO (elimina la fila). Si prefieres el borrado lógico que ya usa la
-- app, cambia por:  update public.pichangol_academias set eliminada = true ...
delete from public.pichangol_academias
where id = 'seed_jartur_elbosque';

-- Matrículas/alumnos demo colgados de esa academia (por si quedaron).
delete from public.pichangol_matriculas
where academia_id = 'seed_jartur_elbosque';

-- Verificación: no debe devolver filas.
select id, dueno, (data->>'nombre') as nombre
from public.pichangol_academias
where id = 'seed_jartur_elbosque';
