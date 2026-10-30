-- LIMPIEZA de canchas DUPLICADAS (misma cancha con 2+ filas por re-registros de
-- prueba). Deja UNA fila por (club, nombre, deporte) y marca las demás como
-- eliminada=true (borrado LÓGICO: la app lo respeta y sobrevive reinstalación).
-- Antes de borrar, REAPUNTA las reservas de las filas perdedoras a la ganadora,
-- para no perder reservas ni romper el panel del dueño.
--
-- GANADORA por grupo: la verificada; a igualdad, la que tiene dueño; a igualdad,
-- la de MAYOR duracion_slot_min (se queda la recién editada, p. ej. 90); y como
-- último desempate, el id.
--
-- Ejecutar en Supabase → SQL Editor. Correr los pasos EN ORDEN.
-- Es idempotente: si ya no hay duplicados, no hace nada.

-- ───────────────────────────────────────────────────────────────────────────
-- PASO 0 (opcional, solo mira): qué se va a conservar y qué se va a retirar.
with ranked as (
  select id, club, nombre, deporte, duracion_slot_min, dueno, verificada,
    row_number() over (
      partition by club, nombre, deporte
      order by verificada desc,
               (coalesce(dueno,'') <> '') desc,
               duracion_slot_min desc,
               id
    ) as rn
  from public.pichangol_canchas
  where coalesce(eliminada, false) = false
)
select rn, case when rn = 1 then 'SE QUEDA' else 'se retira' end as accion,
       id, club, nombre, deporte, duracion_slot_min, dueno, verificada
from ranked
where (club, nombre, deporte) in (
  select club, nombre, deporte from ranked group by club, nombre, deporte having count(*) > 1
)
order by club, nombre, deporte, rn;

-- ───────────────────────────────────────────────────────────────────────────
-- PASO 1: reapuntar las reservas de las filas perdedoras a la ganadora.
with ranked as (
  select id, club, nombre, deporte,
    row_number() over (
      partition by club, nombre, deporte
      order by verificada desc,
               (coalesce(dueno,'') <> '') desc,
               duracion_slot_min desc,
               id
    ) as rn
  from public.pichangol_canchas
  where coalesce(eliminada, false) = false
),
winner as (select club, nombre, deporte, id as win_id from ranked where rn = 1),
loser as (
  select r.id as lose_id, w.win_id
  from ranked r
  join winner w using (club, nombre, deporte)
  where r.rn > 1
)
update public.pichangol_reservas res
set cancha_id = l.win_id
from loser l
where res.cancha_id = l.lose_id
  -- evita chocar con el UNIQUE (cancha_id, fecha, hora_inicio): no reapunta si
  -- la ganadora ya tiene una reserva en ese mismo horario.
  and not exists (
    select 1 from public.pichangol_reservas x
    where x.cancha_id = l.win_id
      and x.fecha = res.fecha
      and x.hora_inicio = res.hora_inicio
  );

-- ───────────────────────────────────────────────────────────────────────────
-- PASO 2: marcar como eliminadas (lógico) las filas perdedoras.
with ranked as (
  select id, club, nombre, deporte,
    row_number() over (
      partition by club, nombre, deporte
      order by verificada desc,
               (coalesce(dueno,'') <> '') desc,
               duracion_slot_min desc,
               id
    ) as rn
  from public.pichangol_canchas
  where coalesce(eliminada, false) = false
)
update public.pichangol_canchas
set eliminada = true
where id in (select id from ranked where rn > 1);

-- ───────────────────────────────────────────────────────────────────────────
-- PASO 3 (verificación): ya no deben quedar grupos con más de una fila activa.
select club, nombre, deporte, count(*) as filas
from public.pichangol_canchas
where coalesce(eliminada, false) = false
group by club, nombre, deporte
having count(*) > 1;
