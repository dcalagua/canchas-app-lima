-- Barrio/zona REAL de la cancha (ej. "Sopocachi", "Equipetrol", "San Borja"),
-- obtenido del reverse-geocode de sus coordenadas al registrarla. Reemplaza al
-- distrito clavado a Lima como la zona VISIBLE al usuario, en cualquier país.
--
-- La app ya opera sin correr esto (el barrio se guarda local en el dispositivo
-- y se muestra al instante); este ALTER hace que el barrio SINCRONICE a la nube
-- / entre dispositivos. Idempotente: seguro de re-correr.

alter table public.pichangol_canchas
  add column if not exists barrio text not null default '';
