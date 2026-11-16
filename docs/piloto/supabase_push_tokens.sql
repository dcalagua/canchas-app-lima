-- ============================================================================
-- Pichangol · Tabla de TOKENS PUSH (FCM) — REQUISITO para chat y llamadas
-- ----------------------------------------------------------------------------
-- Sin esta tabla, la app no puede registrar el token de ningún celular y las
-- Edge Functions (push-mensaje, push-reserva, cancelar-llamada…) no tienen a
-- quién enviarle nada: no llegan notificaciones de chat NI llamadas entrantes
-- con la app cerrada.
--
-- Correr en Supabase → SQL Editor del proyecto del PILOTO. Idempotente.
-- Después de correrlo: cada celular debe ABRIR la app una vez (con sesión y
-- permiso de notificaciones aceptado) para registrar su token.
-- ============================================================================

create table if not exists public.pichangol_push_tokens (
  token        text        primary key,
  email        text        not null,
  plataforma   text        not null default 'android',   -- android | ios
  actualizado  timestamptz not null default now()
);

create index if not exists idx_push_tokens_email
  on public.pichangol_push_tokens (email);

alter table public.pichangol_push_tokens enable row level security;

-- El APK (clave anónima) registra/actualiza/borra el token de SU dispositivo.
drop policy if exists push_tokens_all on public.pichangol_push_tokens;
create policy push_tokens_all
  on public.pichangol_push_tokens for all
  to anon, authenticated
  using (true) with check (true);
