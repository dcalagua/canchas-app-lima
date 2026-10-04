-- Reserva manual del dueño (digitalizar el cuaderno): guarda el teléfono del
-- cliente que reservó por teléfono/WhatsApp. Columna nueva en pichangol_reservas.
--
-- La reserva manual ya funciona sin correr esto (se guarda local en el
-- dispositivo). Este ALTER solo hace que el TELÉFONO del cliente sincronice a la
-- nube / entre dispositivos. Idempotente: seguro de re-correr.

alter table public.pichangol_reservas
  add column if not exists telefono text;

-- Nota: la reserva manual se registra con traida_por_app = FALSE (cliente propio
-- del dueño, fuera de la base de comisión). No requiere cambios de RLS: usa la
-- misma tabla y las mismas policies que las reservas de la app.
