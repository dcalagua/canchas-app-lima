-- DIAGNÓSTICO (solo lectura, no borra nada): busca canchas del MISMO lugar con
-- VARIAS filas (ids distintos) y sus duraciones. Si una cancha aparece con
-- filas > 1 y duraciones mezcladas (p. ej. {60,90}), ESE es el motivo por el
-- que el cliente en otro equipo veía la duración vieja: la app deduplicaba por
-- lugar y en el otro equipo se quedaba con el id que aún tenía 60.
--
-- Ejecutar en Supabase → SQL Editor.

-- 1) Lugares con más de una fila (duplicados de prueba):
select
  club,
  nombre,
  deporte,
  count(*)                       as filas,
  array_agg(duracion_slot_min)   as duraciones,
  array_agg(id)                  as ids
from public.pichangol_canchas
where coalesce(eliminada, false) = false
group by club, nombre, deporte
having count(*) > 1
order by filas desc, club, nombre;

-- 2) Detalle de una cancha puntual (ajusta el filtro a tu caso):
select id, club, nombre, duracion_slot_min, precio_hora, dueno, verificada, eliminada
from public.pichangol_canchas
where club ilike '%joga%'      -- <-- cámbialo por el nombre de tu local
order by nombre, id;
