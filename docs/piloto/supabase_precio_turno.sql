-- PRECIO POR TURNO (pedido del director, 29-sep-2026: "debo tener la opción de
-- cobrar 15 soles la hora o 15 por 1.5 h").
--
-- `precio_turno` > 0  → la cancha cobra ese monto por CADA turno, dure lo que
--                        dure (`duracion_slot_min`).
-- NULL / 0            → cobra por hora: `precio_hora` × duración / 60 (como
--                        siempre).
--
-- Al guardar "por turno", la web y el APK escriben también en `precio_hora` el
-- EQUIVALENTE por hora (precio_turno × 60 / duración), así los APKs viejos que
-- no conocen esta columna cobran lo mismo. Sin esta columna, la web y el APK
-- siguen funcionando (guardan solo el equivalente por hora).
--
-- Correr en QAS (Supabase "Pichangol") y, con autorización, en PCG-PRD.

alter table public.pichangol_canchas
  add column if not exists precio_turno numeric;

comment on column public.pichangol_canchas.precio_turno is
  'Precio por TURNO (duracion_slot_min). NULL/0 = cobra por hora (precio_hora).';
