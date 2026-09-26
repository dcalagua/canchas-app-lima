-- Agenda PRIVADA del usuario (tipo WhatsApp): apodos de contacto, contactos
-- guardados y bloqueados. Se guarda por correo del DUEÑO para que estos datos
-- SIGAN al usuario entre sus dispositivos (teléfono, tablet, etc.).
-- Correr en QAS y en PROD.
create table if not exists public.pichangol_agenda (
  email        text primary key,
  apodos       jsonb default '{}'::jsonb,   -- { "correo_contacto": "Apodo" }
  contactos    jsonb default '[]'::jsonb,   -- ["correo1", "correo2", ...]
  bloqueados   jsonb default '[]'::jsonb,   -- ["correo1", ...]
  actualizado  timestamptz default now()
);
