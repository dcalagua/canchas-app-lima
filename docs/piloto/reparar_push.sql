-- ============================================================================
-- Pichangol · REPARAR PUSH COMPLETO (chat + llamadas) — proyecto del PILOTO
-- ----------------------------------------------------------------------------
-- Restaura las DOS piezas de servidor que necesita el push:
--   1) Tabla `pichangol_push_tokens` (dónde cada celular registra su token FCM)
--   2) Trigger en `pichangol_mensajes` que dispara la Edge Function
--      `push-mensaje` en cada mensaje nuevo (los mensajes de llamada
--      "📞/📹" son los que pintan la pantalla de llamada entrante)
--
-- ANTES DE CORRER: reemplaza TU_ANON_KEY por la anon key del proyecto
-- (Settings → API → anon public). Es la clave PÚBLICA, la misma del APK.
--
-- Correr en Supabase → SQL Editor del proyecto del piloto. Idempotente.
-- Después: abrir Pichangol en CADA celular (con sesión) para registrar su
-- token, y validar con Ajustes → Diagnóstico de push.
-- ============================================================================

-- ── 1) Tabla de tokens ──────────────────────────────────────────────────────
create table if not exists public.pichangol_push_tokens (
  token        text        primary key,
  email        text        not null,
  plataforma   text        not null default 'android',   -- android | ios
  actualizado  timestamptz not null default now()
);

create index if not exists idx_push_tokens_email
  on public.pichangol_push_tokens (email);

alter table public.pichangol_push_tokens enable row level security;

drop policy if exists push_tokens_all on public.pichangol_push_tokens;
create policy push_tokens_all
  on public.pichangol_push_tokens for all
  to anon, authenticated
  using (true) with check (true);

-- ── 2) Trigger mensaje nuevo → Edge Function push-mensaje ───────────────────
create extension if not exists pg_net with schema extensions;

create or replace function public.notificar_push_mensaje()
returns trigger
language plpgsql
security definer
as $$
begin
  perform net.http_post(
    url     := 'https://iuwnpjbxsltgmsybooeg.supabase.co/functions/v1/push-mensaje',
    headers := jsonb_build_object(
      'Content-Type',  'application/json',
      'Authorization', 'Bearer TU_ANON_KEY'
    ),
    body    := jsonb_build_object('record', to_jsonb(NEW))
  );
  return NEW;
end;
$$;

drop trigger if exists trg_push_mensaje on public.pichangol_mensajes;
create trigger trg_push_mensaje
  after insert on public.pichangol_mensajes
  for each row execute function public.notificar_push_mensaje();

-- ── 3) Verificación (correr después; debe listar el trigger y los tokens) ───
select tgname as trigger_creado
  from pg_trigger
 where tgname = 'trg_push_mensaje';

select email, plataforma, actualizado
  from public.pichangol_push_tokens
 order by actualizado desc;
