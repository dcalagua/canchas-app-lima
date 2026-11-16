-- Pichangol · SEÑA + trazabilidad del pago (persistencia en la nube)
-- ------------------------------------------------------------------
-- 1) pichangol_canchas.sena_pct — % de seña que el dueño exige por adelantado.
--    SIN esta columna, guardar la cancha FALLA en la primera pasada (columna
--    desconocida) y el fail-safe reintenta SIN las columnas nuevas → la seña
--    (y en ese guardado también amenidades, superficie, deportes, moneda,
--    servicios extra, hora feliz y barrio) solo quedan en el teléfono del
--    dueño. El jugador lee seña 0 de la nube y paga el 100% online: por eso
--    "no funciona la reserva con seña".
-- 2) pichangol_reservas.medio_pago — por dónde vino la plata (yape / tarjeta /
--    efectivo / sena / manual): chip de trazabilidad en Reservas del dueño.
-- 3) pichangol_reservas.grupo_reserva_id — agrupa las filas de una reserva de
--    varias horas seguidas (18:00–20:00 = 2 filas, un grupo).
--
-- Idempotente: se puede correr las veces que haga falta (no borra ni pisa
-- datos). Ejecutar en Supabase → SQL Editor.

alter table public.pichangol_canchas
  add column if not exists sena_pct integer not null default 0;

alter table public.pichangol_reservas
  add column if not exists medio_pago text not null default '';

alter table public.pichangol_reservas
  add column if not exists grupo_reserva_id text not null default '';

-- Verificación: deben salir las 3 columnas.
select table_name, column_name
  from information_schema.columns
 where (table_name = 'pichangol_canchas' and column_name = 'sena_pct')
    or (table_name = 'pichangol_reservas'
        and column_name in ('medio_pago', 'grupo_reserva_id'));
