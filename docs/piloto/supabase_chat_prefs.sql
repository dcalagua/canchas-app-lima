-- =====================================================================
-- Pichangol · Preferencias de bandeja de chats en la nube (sep-2026)
-- Ejecutar en Supabase → SQL Editor (QAS y luego PRD). Idempotente.
--
-- Guarda, por usuario y por hilo, qué chats ELIMINÓ de su bandeja (y cuándo),
-- cuáles fijó, archivó o silenció. Antes vivía solo en el teléfono
-- (SharedPreferences) → al reinstalar / actualizar / volver a entrar, los
-- chats eliminados reaparecían. Con esta tabla, "eliminas y listo" (WhatsApp):
-- sobrevive reinstalaciones y se comparte entre equipos del mismo usuario.
--
-- `oculto_en` null = visible. Si llega un mensaje MÁS NUEVO que `oculto_en`,
-- la conversación reaparece (misma regla de siempre) y el APK vuelve a poner
-- null.
-- =====================================================================

create table if not exists public.pichangol_chat_prefs (
  email        text        not null,
  hilo         text        not null,
  oculto_en    timestamptz,
  fijado       boolean     not null default false,
  archivado    boolean     not null default false,
  silenciado   boolean     not null default false,
  actualizado  timestamptz not null default now(),
  primary key (email, hilo)
);

create index if not exists idx_chat_prefs_email
  on public.pichangol_chat_prefs (email);

-- RLS: mismo criterio del piloto que las demás tablas (el APK usa la clave
-- anónima; el correo lo pone el APK). Endurecer con auth en una fase posterior.
alter table public.pichangol_chat_prefs enable row level security;

drop policy if exists chat_prefs_select on public.pichangol_chat_prefs;
create policy chat_prefs_select
  on public.pichangol_chat_prefs for select
  to anon, authenticated
  using (true);

drop policy if exists chat_prefs_insert on public.pichangol_chat_prefs;
create policy chat_prefs_insert
  on public.pichangol_chat_prefs for insert
  to anon, authenticated
  with check (true);

drop policy if exists chat_prefs_update on public.pichangol_chat_prefs;
create policy chat_prefs_update
  on public.pichangol_chat_prefs for update
  to anon, authenticated
  using (true)
  with check (true);

drop policy if exists chat_prefs_delete on public.pichangol_chat_prefs;
create policy chat_prefs_delete
  on public.pichangol_chat_prefs for delete
  to anon, authenticated
  using (true);
