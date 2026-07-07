-- =====================================================================
-- Pichangol · Piloto 1 club — reservas reales + anti-doble-reserva
-- Ejecutar en Supabase → SQL Editor. Idempotente (se puede correr 2 veces).
-- =====================================================================

-- 1) Reservas: fecha REAL (ISO "2026-06-27") como fuente de verdad del día,
--    y estado de pago (el dueño confirma el efectivo en cancha).
alter table public.pichangol_reservas
  add column if not exists fecha  text,
  add column if not exists pagado boolean not null default false;

-- 2) Canchas: horario de atención y duración de slot POR cancha (1h/1.5h/2h),
--    y borrado lógico DURABLE (el borrado sobrevive a reinstalar la app; el
--    DELETE fisico suele estar bloqueado por RLS, por eso se usa una bandera).
alter table public.pichangol_canchas
  add column if not exists hora_apertura     text    not null default '07:00',
  add column if not exists hora_cierre       text    not null default '23:00',
  add column if not exists duracion_slot_min integer not null default 60,
  add column if not exists eliminada         boolean not null default false,
  add column if not exists amenidades        jsonb   not null default '[]'::jsonb,
  add column if not exists superficie        text    not null default '';

-- 3) (Opcional, recomendado) Empezar el piloto con reservas limpias: las
--    reservas demo viejas no tienen `fecha`. Descomenta para borrarlas:
-- delete from public.pichangol_reservas where fecha is null;

-- 4) ANTI-DOBLE-RESERVA: un único slot por (cancha, fecha, hora de inicio).
--    Dos jugadores no pueden tomar el mismo horario: el 2º INSERT falla (23505)
--    y la app muestra "ese horario acaba de tomarse".
--    Nota: si hay duplicados previos, este ADD CONSTRAINT fallará; resuélvelos
--    (o corre el delete del paso 3) antes de reintentar.
alter table public.pichangol_reservas
  drop constraint if exists uniq_slot_reserva;
alter table public.pichangol_reservas
  add  constraint uniq_slot_reserva unique (cancha_id, fecha, hora_inicio);


-- =====================================================================
-- PLANTILLA — Inventario del club piloto (rellenar con datos reales)
-- Repetir el bloque VALUES por cada cancha del club. `id` debe ser único
-- y estable. `verificada=true` la habilita para reservar de inmediato.
-- =====================================================================
-- insert into public.pichangol_canchas
--   (id, nombre, club, distrito, deporte, precio_hora, lat, lng,
--    club_fundador, digitalizada, direccion, registrada, dueno, verificada,
--    hora_apertura, hora_cierre, duracion_slot_min)
-- values
--   ('club1-c1', 'Cancha 1', 'NOMBRE DEL CLUB', 'sanBorja', 'futbol', 120.0,
--    -12.108, -76.999, false, true, 'Av. Ejemplo 123', true,
--    'dueno@correo.com', true, '07:00', '23:00', 90)
-- on conflict (id) do update set
--   nombre = excluded.nombre, club = excluded.club, distrito = excluded.distrito,
--   deporte = excluded.deporte, precio_hora = excluded.precio_hora,
--   lat = excluded.lat, lng = excluded.lng, direccion = excluded.direccion,
--   dueno = excluded.dueno, verificada = excluded.verificada,
--   hora_apertura = excluded.hora_apertura, hora_cierre = excluded.hora_cierre,
--   duracion_slot_min = excluded.duracion_slot_min;
-- distrito ∈ {sanBorja, surco, laMolina} · deporte ∈ {futbol, padel, tenis}
