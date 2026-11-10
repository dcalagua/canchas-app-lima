-- Réplica MÍNIMA (solo columnas que usa el agente de marketing) de tablas reales
-- de PCG-PRD, para las pruebas de integración contra un Postgres local.
create table if not exists pichangol_canchas (
  id text primary key, nombre text not null default 'Cancha', club text not null default '',
  distrito text, barrio text, direccion text, deporte text, deportes jsonb not null default '[]'::jsonb,
  precio_hora numeric not null default 100, precio_turno numeric, moneda text,
  lat double precision, lng double precision, registrada boolean not null default true,
  verificada boolean not null default false, eliminada boolean not null default false,
  dueno text, foto_url text, fotos jsonb not null default '[]'::jsonb,
  hora_apertura text, hora_cierre text, duracion_slot_min int,
  descuento_valle int, valle_desde text, valle_hasta text, club_fundador boolean not null default false,
  digitalizada boolean not null default true
);
create table if not exists pichangol_reservas (
  id text primary key, cancha_id text, jugador text, nivel text, fecha text, dia text,
  hora_inicio text, hora_fin text, estado text, traida_por_app boolean, precio numeric,
  sena int, pagado boolean, usuario text, deporte text, moneda text, telefono text,
  extras jsonb, medio_pago text, grupo_reserva_id text, cargo_servicio numeric, cargo_desglose jsonb
);
create unique index if not exists uniq_slot_reserva on pichangol_reservas (cancha_id, fecha, hora_inicio);
create table if not exists pichangol_bloqueos (cancha_id text, fecha text, hora text, creado timestamptz default now(),
  primary key (cancha_id, fecha, hora));
create table if not exists pichangol_descuentos_slot (cancha_id text, fecha text, hora text, pct int,
  primary key (cancha_id, fecha, hora));
create table if not exists pichangol_bonos (id text primary key, dueno text, club text, nombre text, horas int,
  precio numeric, activo boolean, creado timestamptz default now());
create table if not exists pichangol_canchas_cache (id text primary key, nombre text, direccion text,
  lat double precision, lng double precision, deporte text, visto_en timestamptz);
create table if not exists pichangol_canchas_osm (id text primary key, nombre text, deporte text,
  lat double precision, lng double precision, ciudad text, pais text, leisure text, actualizado_en timestamptz);
create table if not exists pichangol_partidos (id text primary key, creador_email text, deporte text, titulo text,
  fecha text, hora text, sede_nombre text, lat double precision, lng double precision, cupos int,
  creado timestamptz default now(), cancha_id text);
