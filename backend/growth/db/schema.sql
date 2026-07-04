-- Esquema de los 3 subsistemas: PUNTOS/PREMIOS, SOLICITUDES POR ZONA,
-- VERIFICACION FISICA (Pichangol).
--
-- Cumplimiento (Ley 29733): NO se guardan datos personales (DNI, recibos,
-- documentos). Las fotos de verificación son del ESTABLECIMIENTO (sitio), no de
-- personas. El consentimiento se registra aparte (puntos vs contacto).

-- =========================================================================
-- A. PUNTOS Y PREMIOS
-- =========================================================================

-- Reglas/parametría configurable (NADA hardcodeado en la lógica).
create table if not exists config_incentivos (
  clave text primary key,
  valor text not null
);
-- Semillas sugeridas (ajustables):
--   puntos_traer_cancha=500, puntos_invitar_jugador=100, puntos_pedir_cancha=50,
--   equivalencia_puntos_por_sol=100, tope_mensual_premios_pichangol_soles=500,
--   tope_solicitudes_usuario_mes=5, umbral_ia_verificacion=70

create table if not exists puntos_movimientos (
  id          bigserial primary key,
  usuario_id  text not null,
  accion      text not null,                 -- traer_cancha|invitar_jugador|pedir_cancha
  puntos      int  not null,
  estado      text not null default 'pendiente'
              check (estado in ('pendiente','liberado','anulado')),
  ref_tipo    text,                           -- cancha|solicitud|jugador
  ref_id      text,
  creado_en   timestamptz not null default now(),
  liberado_en timestamptz
);
create index if not exists idx_mov_usuario on puntos_movimientos (usuario_id);
create index if not exists idx_mov_ref on puntos_movimientos (ref_tipo, ref_id);

create table if not exists premios_canjes (
  id            bigserial primary key,
  usuario_id    text not null,
  puntos_usados int  not null,
  tipo_premio   text not null,
  vale_id       text not null,
  fuente_financiamiento text not null
                check (fuente_financiamiento in ('pichangol','dueno')),
  estado        text not null default 'emitido',
  valor_soles   numeric(10,2) not null default 0,
  creado_en     timestamptz not null default now()
);

-- =========================================================================
-- B. SOLICITUDES POR ZONA ("pide tu cancha")
-- =========================================================================
create table if not exists solicitudes_cancha (
  id                  bigserial primary key,
  usuario_id          text not null,
  nombre_cancha_libre text not null,
  direccion_texto     text not null,
  lat                 double precision,
  lng                 double precision,
  distrito            text,
  zona                text check (zona in ('lima_norte','lima_sur','lima_este','lima_moderna','callao')),
  estado              text not null default 'solicitada'
                      check (estado in ('solicitada','en_captacion','registrada','descartada')),
  cancha_id           text,
  creado_en           timestamptz not null default now()
);
create index if not exists idx_sol_zona on solicitudes_cancha (zona);

-- =========================================================================
-- C. VERIFICACION FISICA (carril informal)
-- =========================================================================
create table if not exists verificadores (
  id     bigserial primary key,
  nombre text not null,
  zona   text not null,
  tipo   text not null check (tipo in ('por_encargo','dedicado')),
  activo boolean not null default true
);

create table if not exists verificaciones_fisicas (
  id              bigserial primary key,
  cancha_id       text not null,
  solicitud_id    bigint references solicitudes_cancha,
  motivo          text check (motivo in ('sin_documentos','ia_no_concluyente','alto_valor')),
  verificador_id  bigint references verificadores,
  estado          text not null default 'agendada'
                  check (estado in ('no_requerida','agendada','en_sitio','confirmada','rechazada')),
  fotos_geo_urls  jsonb not null default '[]'::jsonb,  -- fotos del SITIO (no personales)
  lat_sitio       double precision,
  lng_sitio       double precision,
  firma_verificador text,
  observaciones   text,
  metodo          text,                 -- documental|en_sitio (interno; insignia pública es única)
  creado_en       timestamptz not null default now(),
  cerrada_en      timestamptz
);

-- =========================================================================
-- TRANSVERSAL: consentimientos (puntos y contacto, SEPARADOS)
-- =========================================================================
create table if not exists consentimientos_growth (
  id         bigserial primary key,
  sujeto_id  text not null,
  tipo       text not null check (tipo in ('puntos','contacto')),
  otorgado   boolean not null,
  fecha      timestamptz not null default now(),
  unique (sujeto_id, tipo)
);

-- =========================================================================
-- E. CONVOCATORIAS ("pichangas" programadas con cupos + lista de espera)
--    Reparto de cupos por 3 modos configurables: orden_llegada|sorteo|equidad.
-- =========================================================================
create table if not exists convocatorias (
  id              bigserial primary key,
  club_id         text not null,
  titulo          text not null,
  deporte         text not null default 'futbol',
  cupos           integer not null default 14,
  estado          text not null default 'abierta' check (estado in ('abierta','cerrada')),
  categoria       text,                 -- master|menor|libre
  fecha_partido   text,                 -- ISO/texto del partido (display)
  apertura        timestamptz,          -- desde cuándo se puede inscribir
  cierre          timestamptz,          -- hasta cuándo (y cuándo se resuelve)
  modo_asignacion text check (modo_asignacion in ('orden_llegada','sorteo','equidad')),
  semilla         text,                 -- fijada al cerrar (sorteo reproducible)
  creado_por      text,
  creado_en       timestamptz not null default now(),
  cerrado_en      timestamptz
);

create table if not exists inscripciones_convocatoria (
  id              bigserial primary key,
  convocatoria_id bigint not null references convocatorias,
  socio_id        text not null,
  socio_nombre    text not null,
  estado          text not null default 'pendiente'
                  check (estado in ('pendiente','confirmado','lista_espera','cancelado')),
  posicion        integer,              -- congelada al cerrar
  asistio         boolean,              -- marcada por el admin tras el partido
  creado_en       timestamptz not null default now(),
  unique (convocatoria_id, socio_id)
);
