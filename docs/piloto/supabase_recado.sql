-- Recado / estado (tipo WhatsApp) en el perfil público del usuario.
-- Texto corto que el usuario pone en "Mensajes → 3 puntos → Mi recado" y que
-- sus contactos ven en la cabecera del chat.
-- Correr en QAS y en PROD.
alter table public.pichangol_perfiles
  add column if not exists recado text;
