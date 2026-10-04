-- ============================================================================
-- Pichangol · Cargo por servicio en las reservas (fase 3, sep-2026)
-- ----------------------------------------------------------------------------
-- Agrega a pichangol_reservas lo que el JUGADOR pagó además del precio de la
-- cancha: `cargo_servicio` (unidad mayor de la moneda de la reserva; 0 = sin
-- cargo o línea apagada) y `cargo_desglose` (componentes congelados al pagar:
-- [{clave, nombre, pct, detalle, monto_centimos}]). Lo escriben el APK y la
-- web al confirmar el pago; la fuente contable sigue siendo el backend growth
-- (liquidación / cobro_web). Sirve para que "Mis reservas" del app y el
-- comprobante web muestren el mismo total pagado en cualquier equipo.
--
-- Correr en Supabase → SQL Editor (QAS "Pichangol"; PRD solo con autorización).
-- Idempotente. Sin la columna, el APK y la web siguen funcionando: escriben la
-- reserva sin el cargo (tolerante) y el comprobante lo toma del backend.
-- ============================================================================

alter table public.pichangol_reservas
  add column if not exists cargo_servicio numeric(10,2) not null default 0;

alter table public.pichangol_reservas
  add column if not exists cargo_desglose jsonb not null default '[]'::jsonb;
