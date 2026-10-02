-- =====================================================================
-- Pichangol · Chat de academia (Etapa A: Realtime, sin push)
-- Ejecutar en Supabase → SQL Editor. Idempotente (se puede correr 2 veces).
--
-- Chat 1:1 profe ↔ cuenta de alumno, por academia. Cada fila = un mensaje.
-- El `hilo` = "academiaId|cuentaEmail" es la clave de la conversación (por eso
-- va indexado): el app filtra el stream por `hilo`. La bandeja del profe
-- filtra por `academia_id`.
-- =====================================================================

create table if not exists public.pichangol_mensajes (
  id           text        primary key,
  hilo         text        not null,
  academia_id  text        not null,
  cuenta_email text        not null,
  autor_email  text        not null,
  autor_nombre text        not null default '',
  es_profe     boolean     not null default false,
  texto        text        not null,
  creado       timestamptz not null default now()
);

create index if not exists idx_mensajes_hilo
  on public.pichangol_mensajes (hilo, creado);
create index if not exists idx_mensajes_academia
  on public.pichangol_mensajes (academia_id, creado);

-- --------------------------------------------------------------------
-- Realtime: hay que agregar la tabla a la publicación `supabase_realtime`
-- para que el app reciba los mensajes nuevos en vivo (el .stream() del SDK).
-- Idempotente: si ya está agregada, ignora el error.
-- --------------------------------------------------------------------
do $$
begin
  begin
    alter publication supabase_realtime add table public.pichangol_mensajes;
  exception
    when duplicate_object then null; -- ya estaba en la publicación
  end;
end $$;

-- --------------------------------------------------------------------
-- RLS: mismo criterio del piloto que las demás tablas (el APK usa la clave
-- anónima). Lectura/inserción al rol anon. Sin update/delete (los mensajes no
-- se editan). Endurecer por dueño/alumno en una fase posterior (auth).
-- --------------------------------------------------------------------
alter table public.pichangol_mensajes enable row level security;

drop policy if exists mensajes_lectura on public.pichangol_mensajes;
create policy mensajes_lectura
  on public.pichangol_mensajes for select
  to anon, authenticated
  using (true);

drop policy if exists mensajes_insert on public.pichangol_mensajes;
create policy mensajes_insert
  on public.pichangol_mensajes for insert
  to anon, authenticated
  with check (true);

-- =====================================================================
-- Pichangol · Push del chat (Etapa B: FCM)
-- Tokens de dispositivo por cuenta (correo). La Edge Function `push-mensaje`
-- los usa para enviar la notificación al DESTINATARIO cuando entra un mensaje.
-- Un correo puede tener varios tokens (varios dispositivos); un token es único.
-- =====================================================================

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

-- --------------------------------------------------------------------
-- Webhook: al INSERT en pichangol_mensajes, dispara la Edge Function
-- `push-mensaje`. Se configura desde el dashboard (Database → Webhooks):
--   Tabla: pichangol_mensajes · Evento: INSERT · Tipo: Supabase Edge Functions
--   Función: push-mensaje. (Ver docs/piloto/push_fcm_setup.md)
-- --------------------------------------------------------------------
