-- HORA FELIZ configurable: ventana (desde/hasta) elegida por el dueño.
-- Corre esto en Supabase → SQL Editor (proyecto del piloto).
--
-- Vacío = default histórico (hasta las 12:00, las mañanas). Si "hasta" es
-- menor o igual que "desde", la ventana cruza medianoche (cancha nocturna,
-- p. ej. 22:00 → 02:00).

alter table public.pichangol_canchas
  add column if not exists valle_desde text not null default '',
  add column if not exists valle_hasta text not null default '';
