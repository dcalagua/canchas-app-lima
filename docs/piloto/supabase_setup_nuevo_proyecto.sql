-- =====================================================================
-- Pichangol · SETUP de un proyecto Supabase NUEVO (desde cero)
-- Ejecutar en Supabase → SQL Editor. Idempotente (se puede correr 2 veces).
-- Crea las tablas que usa el APK (canchas + reservas) con TODAS las columnas,
-- el anti-doble-reserva y las políticas RLS del piloto.
-- (La tabla `growth_state` del backend NO va aquí: el backend growth la crea
--  solo al arrancar con DATABASE_URL.)
-- =====================================================================

-- 1) CANCHAS ----------------------------------------------------------
create table if not exists public.pichangol_canchas (
  id                text primary key,
  nombre            text not null default 'Cancha',
  club              text not null default '',
  distrito          text,                 -- sanBorja | surco | laMolina
  deporte           text,                 -- PRINCIPAL: futbol|padel|tenis|pickleball|voley|basquet
  deportes          jsonb   not null default '[]'::jsonb, -- loza multiuso: todos los deportes jugables
  precio_hora       numeric not null default 100,
  lat               double precision,
  lng               double precision,
  club_fundador     boolean not null default false,
  digitalizada      boolean not null default true,
  direccion         text,
  registrada        boolean not null default true,
  foto_url          text,
  fotos             jsonb   not null default '[]'::jsonb,
  dueno             text    not null default '',
  verificada        boolean not null default true,
  hora_apertura     text    not null default '07:00',
  hora_cierre       text    not null default '23:00',
  duracion_slot_min integer not null default 60,
  eliminada         boolean not null default false,
  amenidades        jsonb   not null default '[]'::jsonb, -- servicios (vestuario, parking, luces…)
  superficie        text    not null default ''           -- tipo de piso (loza, arcilla, grass sintético…)
);

-- 2) RESERVAS ---------------------------------------------------------
create table if not exists public.pichangol_reservas (
  id             text primary key,
  cancha_id      text not null,
  jugador        text not null default 'Jugador',
  nivel          text not null default '',
  fecha          text,                    -- ISO "2026-06-27" (día real)
  dia            text not null default 'Hoy',
  hora_inicio    text not null default '',
  hora_fin       text not null default '',
  estado         text not null default 'confirmada',
  traida_por_app boolean not null default true,
  precio         numeric not null default 0,
  sena           integer not null default 0,
  pagado         boolean not null default false,
  usuario        text not null default '',
  deporte        text not null default ''  -- deporte elegido para el slot (loza multiuso)
);

-- Migración idempotente (proyectos ya creados): agrega las columnas nuevas de
-- la loza multiuso si faltan. Sin esto, la app igual funciona (fail-safe: guarda
-- sin la columna), pero no persiste el set de deportes / el deporte del slot.
alter table public.pichangol_canchas
  add column if not exists deportes jsonb not null default '[]'::jsonb;
alter table public.pichangol_reservas
  add column if not exists deporte text not null default '';

-- Anti-doble-reserva: un único slot por (cancha, fecha, hora de inicio). La
-- agenda es COMPARTIDA entre deportes (misma superficie): el UNIQUE NO incluye
-- deporte, así reservar ocupa la cancha para todos los deportes.
alter table public.pichangol_reservas
  drop constraint if exists uniq_slot_reserva;
alter table public.pichangol_reservas
  add  constraint uniq_slot_reserva unique (cancha_id, fecha, hora_inicio);

-- 3) RLS (piloto) -----------------------------------------------------
-- El APK usa la anon key (todavía no hay Supabase Auth). Para el piloto se
-- permite acceso completo con la anon key. Endurecer con auth más adelante.
alter table public.pichangol_canchas  enable row level security;
alter table public.pichangol_reservas enable row level security;

drop policy if exists canchas_pilot_all  on public.pichangol_canchas;
drop policy if exists reservas_pilot_all on public.pichangol_reservas;

create policy canchas_pilot_all on public.pichangol_canchas
  for all to anon, authenticated using (true) with check (true);
create policy reservas_pilot_all on public.pichangol_reservas
  for all to anon, authenticated using (true) with check (true);

-- 4) (Opcional) Inventario del club piloto — descomentar y rellenar real.
-- insert into public.pichangol_canchas
--   (id, nombre, club, distrito, deporte, precio_hora, lat, lng,
--    club_fundador, digitalizada, direccion, registrada, dueno, verificada,
--    hora_apertura, hora_cierre, duracion_slot_min)
-- values
--   ('club1-c1', 'Cancha 1', 'NOMBRE DEL CLUB', 'sanBorja', 'futbol', 120.0,
--    -12.108, -76.999, false, true, 'Av. Ejemplo 123', true,
--    'dueno@correo.com', true, '07:00', '23:00', 90)
-- on conflict (id) do update set
--   nombre = excluded.nombre, verificada = excluded.verificada;
