-- Pichangol · duración del turno por cancha (persistencia en la nube)
-- ------------------------------------------------------------------
-- Asegura que la columna `duracion_slot_min` exista en `pichangol_canchas`.
-- Es la duración en MINUTOS del bloque reservable (60 = 1h, 90 = 1h 30min,
-- 120 = 2h). El APK ya la envía y la lee; sin esta columna, editar la
-- duración solo vive en el teléfono donde se editó (el fail-safe la descarta
-- al subir) y otro equipo / una reinstalación la vería de nuevo en 1h.
--
-- Idempotente: se puede correr las veces que haga falta (no borra ni pisa
-- datos). Ejecutar en Supabase → SQL Editor.

alter table public.pichangol_canchas
  add column if not exists duracion_slot_min integer not null default 60;

-- Normaliza cualquier valor inválido (0/negativo/nulo colado antes) a 60.
update public.pichangol_canchas
   set duracion_slot_min = 60
 where duracion_slot_min is null
    or duracion_slot_min <= 0;
