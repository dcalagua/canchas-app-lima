-- Responder citando + Reenviar en el chat (tipo WhatsApp). Correr en QAS y PROD.
alter table public.pichangol_mensajes add column if not exists resp_texto text default '';
alter table public.pichangol_mensajes add column if not exists resp_autor text default '';
alter table public.pichangol_mensajes add column if not exists reenviado  boolean default false;
alter table public.pichangol_mensajes add column if not exists resp_media text default '';
