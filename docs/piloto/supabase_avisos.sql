-- =====================================================================
-- Pichangol · Avisos push (canal genérico) — usado por los RETOS P2P
-- Ejecutar en Supabase → SQL Editor. Idempotente (se puede correr 2 veces).
--
-- Los retos viven en el backend growth (Railway), no en Supabase, así que el
-- push del chat (push-mensaje) no los cubre. Este canal cierra ese hueco: el
-- APK que hace la acción (retar / aceptar / reportar) INSERTA una fila con el
-- destinatario y el texto; un Database Webhook dispara la Edge Function
-- `push-aviso`, que busca los tokens del correo en `pichangol_push_tokens` y
-- envía la notificación FCM. Reusa el MISMO secret FCM_SERVICE_ACCOUNT del chat.
-- Sirve para retos hoy y para cualquier aviso puntual más adelante.
-- =====================================================================

create table if not exists public.pichangol_avisos (
  id      bigint      generated always as identity primary key,
  email   text        not null,                 -- destinatario (correo)
  titulo  text        not null default 'Pichangol',
  cuerpo  text        not null,
  tipo    text        not null default 'aviso', -- reto | aviso | ...
  data    jsonb       not null default '{}'::jsonb,
  creado  timestamptz not null default now()
);

create index if not exists idx_avisos_email
  on public.pichangol_avisos (email, creado);

alter table public.pichangol_avisos enable row level security;

-- El APK (clave anónima) inserta avisos; lectura al mismo rol (diagnóstico).
-- Sin update/delete. Endurecer por remitente en una fase posterior (auth).
drop policy if exists avisos_insert on public.pichangol_avisos;
create policy avisos_insert
  on public.pichangol_avisos for insert
  to anon, authenticated
  with check (true);

drop policy if exists avisos_lectura on public.pichangol_avisos;
create policy avisos_lectura
  on public.pichangol_avisos for select
  to anon, authenticated
  using (true);

-- --------------------------------------------------------------------
-- Webhook: al INSERT en pichangol_avisos, dispara la Edge Function
-- `push-aviso`. Se configura desde el dashboard (Database → Webhooks):
--   Tabla: pichangol_avisos · Evento: INSERT · Tipo: Supabase Edge Functions
--   Función: push-aviso. (Ver docs/piloto/push_retos_webhook.md)
-- --------------------------------------------------------------------
