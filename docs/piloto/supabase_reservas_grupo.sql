-- Reserva de VARIAS HORAS seguidas: columna que agrupa las horas de un mismo
-- bloque (18:00–20:00 = 2 filas con el mismo grupo). Idempotente.
--
-- Correr en el SQL Editor del proyecto Supabase (QAS y PROD).
--
-- La app es fail-safe: si esta columna aún NO existe, las reservas de una sola
-- hora funcionan igual; las de varias horas también se guardan, pero sin el
-- grupo en la nube (el agrupado en "Mis reservas" sigue funcionando LOCAL).
-- Con la columna, el bloque persiste y se agrupa también entre dispositivos.

alter table public.pichangol_reservas
  add column if not exists grupo_reserva_id text;

-- (Opcional) índice para buscar rápido las horas de un mismo bloque.
create index if not exists pichangol_reservas_grupo_idx
  on public.pichangol_reservas (grupo_reserva_id);
