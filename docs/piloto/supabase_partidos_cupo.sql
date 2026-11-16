-- PARTIDOS: cupo respetado contra el servidor (fix "3 de 2 jugadores").
-- Corre esto en Supabase → SQL Editor (proyecto del piloto).
--
-- La app ahora verifica el cupo contra la BD al apuntarse y, si dos jugadores
-- entran al último cupo a la vez, el sobrante se baja solo POR ORDEN DE
-- LLEGADA. Esta columna da ese orden (quién se apuntó primero).

alter table public.pichangol_grupo_miembros
  add column if not exists creado timestamptz not null default now();
