-- ============================================================================
-- Pichangol · Trazabilidad del medio de pago en las reservas
-- ----------------------------------------------------------------------------
-- Agrega la columna `medio_pago` a pichangol_reservas para saber CÓMO pagó el
-- jugador cada reserva: 'yape' | 'tarjeta' (online, ya cobrado por Culqi) |
-- 'efectivo' (paga en la cancha) | 'sena' (adelantó una parte) | 'manual'
-- (reserva que el dueño cargó a mano). Se usa en Reservas del dueño y en los
-- reportes/estados de cuenta.
--
-- Correr en Supabase → SQL Editor. Idempotente.
-- ============================================================================

alter table public.pichangol_reservas
  add column if not exists medio_pago text default '';

-- (opcional) índice para filtrar por medio en reportes.
create index if not exists idx_reservas_medio_pago
  on public.pichangol_reservas (medio_pago);
