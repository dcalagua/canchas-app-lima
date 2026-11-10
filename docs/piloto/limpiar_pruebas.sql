-- ============================================================================
-- Pichangol · Dejar TODO VIRGEN para probar de cero (academias + alumnos)
-- ----------------------------------------------------------------------------
-- Corre esto en Supabase → SQL Editor del proyecto de Pichangol.
-- Borra TODAS las academias y matrículas (alumnos) de la nube. NO se puede
-- deshacer. No toca cuentas, tokens de push ni canchas.
--
-- Después de correrlo:
--   1) En la torre de control /admin → "Mantenimiento (pruebas)" →
--      "Borrar suscripciones de alumnos" (para que no queden débitos huérfanos).
--   2) En cada teléfono: la app → Ajustes → "Empezar de cero" (limpia lo local).
-- ============================================================================

-- Academias (se recrean al registrarlas de nuevo).
delete from public.pichangol_academias;

-- Matrículas de alumnos (incluye las cuotas embebidas en la columna data).
delete from public.pichangol_matriculas;

-- Campeonatos de academias (opcional; van atados a academias que ya no existen).
delete from public.pichangol_campeonatos;

-- (Opcional) Mensajes de chat de academias. Descoméntalo solo si también quieres
-- borrar las conversaciones de las academias de prueba:
-- delete from public.pichangol_mensajes where academia_id is not null;

-- Verificación rápida: deben quedar en 0.
select
  (select count(*) from public.pichangol_academias)  as academias,
  (select count(*) from public.pichangol_matriculas)  as matriculas;
