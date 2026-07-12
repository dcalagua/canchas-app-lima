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
