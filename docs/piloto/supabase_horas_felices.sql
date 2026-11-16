-- Hora feliz / precios dinámicos: descuento (%) que el dueño aplica a las horas
-- valle (mañanas) para llenar cancha vacía. Columna nueva en pichangol_canchas.
--
-- La función ya opera sin correr esto (se guarda local en el dispositivo); este
-- ALTER hace que el descuento SINCRONICE a la nube / entre dispositivos.
-- Idempotente: seguro de re-correr.

alter table public.pichangol_canchas
  add column if not exists descuento_valle integer not null default 0;
