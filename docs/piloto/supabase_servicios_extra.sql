-- =====================================================================
-- Pichangol · Servicios extra de la reserva (árbitro / pelotero / …)
-- Ejecutar en Supabase → SQL Editor. IDEMPOTENTE.
--
-- El dueño define qué servicios ofrece su cancha y a qué precio; el jugador los
-- agrega al reservar y suman a su total; el dueño los ve en sus cobros.
--   • pichangol_canchas.servicios_extra  → catálogo del dueño (JSONB, [{clave,precio}])
--   • pichangol_reservas.extras          → los elegidos en esa reserva (JSONB)
-- La app es fail-safe: si estas columnas no existen, igual reserva (sin extras).
-- =====================================================================

alter table if exists public.pichangol_canchas
  add column if not exists servicios_extra jsonb not null default '[]'::jsonb;

alter table if exists public.pichangol_reservas
  add column if not exists extras jsonb not null default '[]'::jsonb;
