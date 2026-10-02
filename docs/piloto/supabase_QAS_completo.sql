-- =====================================================================
-- Pichangol · SETUP COMPLETO de un proyecto Supabase NUEVO (QAS o PROD)
-- Ejecutar TODO de una vez en Supabase → SQL Editor. Idempotente (se puede
-- correr varias veces). Consolida todas las tablas que usa el APK.
--
-- NO incluye la tabla `growth_state` del backend: el backend growth la crea
-- solo al arrancar con DATABASE_URL apuntando a este proyecto.
--
-- Generado a partir de los scripts docs/piloto/supabase_*.sql (fuente de verdad).
-- =====================================================================



-- ###################################################################
-- ## supabase_setup_nuevo_proyecto.sql
-- ###################################################################

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
-- Moneda por cancha (multi-país): se congela al registrar según el país. Las
-- canchas viejas quedan con '' → la app las muestra como 'S/' (Perú). La reserva
-- guarda la moneda de la cancha al reservar.
alter table public.pichangol_canchas
  add column if not exists moneda text not null default '';
alter table public.pichangol_reservas
  add column if not exists moneda text not null default '';

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


-- ###################################################################
-- ## supabase_barrio.sql
-- ###################################################################

-- Barrio/zona REAL de la cancha (ej. "Sopocachi", "Equipetrol", "San Borja"),
-- obtenido del reverse-geocode de sus coordenadas al registrarla. Reemplaza al
-- distrito clavado a Lima como la zona VISIBLE al usuario, en cualquier país.
--
-- La app ya opera sin correr esto (el barrio se guarda local en el dispositivo
-- y se muestra al instante); este ALTER hace que el barrio SINCRONICE a la nube
-- / entre dispositivos. Idempotente: seguro de re-correr.

alter table public.pichangol_canchas
  add column if not exists barrio text not null default '';


-- ###################################################################
-- ## supabase_reservas.sql
-- ###################################################################

-- =====================================================================
-- Pichangol · Piloto 1 club — reservas reales + anti-doble-reserva
-- Ejecutar en Supabase → SQL Editor. Idempotente (se puede correr 2 veces).
-- =====================================================================

-- 1) Reservas: fecha REAL (ISO "2026-06-27") como fuente de verdad del día,
--    y estado de pago (el dueño confirma el efectivo en cancha).
alter table public.pichangol_reservas
  add column if not exists fecha  text,
  add column if not exists pagado boolean not null default false;

-- 2) Canchas: horario de atención y duración de slot POR cancha (1h/1.5h/2h),
--    y borrado lógico DURABLE (el borrado sobrevive a reinstalar la app; el
--    DELETE fisico suele estar bloqueado por RLS, por eso se usa una bandera).
alter table public.pichangol_canchas
  add column if not exists hora_apertura     text    not null default '07:00',
  add column if not exists hora_cierre       text    not null default '23:00',
  add column if not exists duracion_slot_min integer not null default 60,
  add column if not exists eliminada         boolean not null default false,
  add column if not exists amenidades        jsonb   not null default '[]'::jsonb,
  add column if not exists superficie        text    not null default '';

-- 3) (Opcional, recomendado) Empezar el piloto con reservas limpias: las
--    reservas demo viejas no tienen `fecha`. Descomenta para borrarlas:
-- delete from public.pichangol_reservas where fecha is null;

-- 4) ANTI-DOBLE-RESERVA: un único slot por (cancha, fecha, hora de inicio).
--    Dos jugadores no pueden tomar el mismo horario: el 2º INSERT falla (23505)
--    y la app muestra "ese horario acaba de tomarse".
--    Nota: si hay duplicados previos, este ADD CONSTRAINT fallará; resuélvelos
--    (o corre el delete del paso 3) antes de reintentar.
alter table public.pichangol_reservas
  drop constraint if exists uniq_slot_reserva;
alter table public.pichangol_reservas
  add  constraint uniq_slot_reserva unique (cancha_id, fecha, hora_inicio);


-- =====================================================================
-- PLANTILLA — Inventario del club piloto (rellenar con datos reales)
-- Repetir el bloque VALUES por cada cancha del club. `id` debe ser único
-- y estable. `verificada=true` la habilita para reservar de inmediato.
-- =====================================================================
-- insert into public.pichangol_canchas
--   (id, nombre, club, distrito, deporte, precio_hora, lat, lng,
--    club_fundador, digitalizada, direccion, registrada, dueno, verificada,
--    hora_apertura, hora_cierre, duracion_slot_min)
-- values
--   ('club1-c1', 'Cancha 1', 'NOMBRE DEL CLUB', 'sanBorja', 'futbol', 120.0,
--    -12.108, -76.999, false, true, 'Av. Ejemplo 123', true,
--    'dueno@correo.com', true, '07:00', '23:00', 90)
-- on conflict (id) do update set
--   nombre = excluded.nombre, club = excluded.club, distrito = excluded.distrito,
--   deporte = excluded.deporte, precio_hora = excluded.precio_hora,
--   lat = excluded.lat, lng = excluded.lng, direccion = excluded.direccion,
--   dueno = excluded.dueno, verificada = excluded.verificada,
--   hora_apertura = excluded.hora_apertura, hora_cierre = excluded.hora_cierre,
--   duracion_slot_min = excluded.duracion_slot_min;
-- distrito ∈ {sanBorja, surco, laMolina} · deporte ∈ {futbol, padel, tenis}


-- ###################################################################
-- ## supabase_reserva_manual.sql
-- ###################################################################

-- Reserva manual del dueño (digitalizar el cuaderno): guarda el teléfono del
-- cliente que reservó por teléfono/WhatsApp. Columna nueva en pichangol_reservas.
--
-- La reserva manual ya funciona sin correr esto (se guarda local en el
-- dispositivo). Este ALTER solo hace que el TELÉFONO del cliente sincronice a la
-- nube / entre dispositivos. Idempotente: seguro de re-correr.

alter table public.pichangol_reservas
  add column if not exists telefono text;

-- Nota: la reserva manual se registra con traida_por_app = FALSE (cliente propio
-- del dueño, fuera de la base de comisión). No requiere cambios de RLS: usa la
-- misma tabla y las mismas policies que las reservas de la app.


-- ###################################################################
-- ## supabase_servicios_extra.sql
-- ###################################################################

-- =====================================================================
-- Pichangol · Servicios extra de la reserva (árbitro / pelotero / …)
-- Ejecutar en Supabase → SQL Editor. IDEMPOTENTE.
--
-- El dueño define qué servicios ofrece su cancha y a qué precio; el jugador los
-- agrega al reservar y suman a su total; el dueño los ve en sus cobros.
--   • pichangol_canchas.servicios_extra  → catálogo del dueño (JSONB, [{clave,precio}])
--   • pichangol_reservas.extras          → los elegidos en esa reserva (JSONB)
-- La app es fail-safe: si estas columnas no existen, igual reserva (sin extras).
-- =====================================================================

alter table if exists public.pichangol_canchas
  add column if not exists servicios_extra jsonb not null default '[]'::jsonb;

alter table if exists public.pichangol_reservas
  add column if not exists extras jsonb not null default '[]'::jsonb;


-- ###################################################################
-- ## supabase_horas_felices.sql
-- ###################################################################

-- Hora feliz / precios dinámicos: descuento (%) que el dueño aplica a las horas
-- valle (mañanas) para llenar cancha vacía. Columna nueva en pichangol_canchas.
--
-- La función ya opera sin correr esto (se guarda local en el dispositivo); este
-- ALTER hace que el descuento SINCRONICE a la nube / entre dispositivos.
-- Idempotente: seguro de re-correr.

alter table public.pichangol_canchas
  add column if not exists descuento_valle integer not null default 0;


-- ###################################################################
-- ## supabase_academias.sql
-- ###################################################################

-- =====================================================================
-- Pichangol · Academias en la nube (sobreviven a reinstalar el APK)
-- Ejecutar en Supabase → SQL Editor. Idempotente (se puede correr 2 veces).
--
-- Antes: las academias vivían solo en el celular (SharedPreferences) y se
-- perdían al desinstalar. Ahora se guardan aquí (columna `data` jsonb con la
-- academia completa) y el APK las vuelve a cargar al arrancar.
-- =====================================================================

create table if not exists public.pichangol_academias (
  id         text primary key,
  dueno      text,
  data       jsonb       not null,
  eliminada  boolean     not null default false,
  updated_at timestamptz not null default now()
);

-- Índice para listar rápido las no eliminadas.
create index if not exists idx_academias_activas
  on public.pichangol_academias (eliminada);

-- --------------------------------------------------------------------
-- RLS: el directorio de academias es PÚBLICO (cualquiera las ve para
-- matricularse). El APK usa la clave anónima, así que damos lectura y
-- escritura al rol anon (mismo criterio que `pichangol_canchas` en el
-- piloto). Endurecer con auth por dueño en una fase posterior.
-- --------------------------------------------------------------------
alter table public.pichangol_academias enable row level security;

drop policy if exists academias_lectura on public.pichangol_academias;
create policy academias_lectura
  on public.pichangol_academias for select
  to anon, authenticated
  using (true);

drop policy if exists academias_insert on public.pichangol_academias;
create policy academias_insert
  on public.pichangol_academias for insert
  to anon, authenticated
  with check (true);

drop policy if exists academias_update on public.pichangol_academias;
create policy academias_update
  on public.pichangol_academias for update
  to anon, authenticated
  using (true) with check (true);


-- ###################################################################
-- ## supabase_matriculas.sql
-- ###################################################################

-- =====================================================================
-- Pichangol · Matrículas en la nube ("Unirme con código")
-- Ejecutar en Supabase → SQL Editor. Idempotente (se puede correr 2 veces).
--
-- Permite que un alumno se una a una academia con su CÓDIGO desde su propio
-- celular y que el PROFE lo vea en el suyo. Cada fila = un alumno matriculado
-- (columna `data` jsonb con el Alumno completo). `academia_id` y `email` van
-- sueltos para filtrar rápido.
-- =====================================================================

create table if not exists public.pichangol_matriculas (
  id          text primary key,
  academia_id text        not null,
  email       text,
  data        jsonb       not null,
  eliminada   boolean     not null default false,
  updated_at  timestamptz not null default now()
);

-- Índices para las dos consultas del app: por academia (profe) y por email (alumno).
create index if not exists idx_matriculas_academia
  on public.pichangol_matriculas (academia_id);
create index if not exists idx_matriculas_email
  on public.pichangol_matriculas (email);

-- --------------------------------------------------------------------
-- RLS: mismo criterio del piloto que `pichangol_academias` (el APK usa la
-- clave anónima). Lectura/escritura al rol anon. Endurecer por dueño/alumno
-- en una fase posterior (auth). No se guarda DNI aquí (Ley 29733).
-- --------------------------------------------------------------------
alter table public.pichangol_matriculas enable row level security;

drop policy if exists matriculas_lectura on public.pichangol_matriculas;
create policy matriculas_lectura
  on public.pichangol_matriculas for select
  to anon, authenticated
  using (true);

drop policy if exists matriculas_insert on public.pichangol_matriculas;
create policy matriculas_insert
  on public.pichangol_matriculas for insert
  to anon, authenticated
  with check (true);

drop policy if exists matriculas_update on public.pichangol_matriculas;
create policy matriculas_update
  on public.pichangol_matriculas for update
  to anon, authenticated
  using (true) with check (true);


-- ###################################################################
-- ## supabase_mensajes.sql
-- ###################################################################

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


-- ###################################################################
-- ## supabase_resenas.sql
-- ###################################################################

-- =====================================================================
-- Pichangol · Reseñas de canchas (⭐ + comentario)
-- Reemplaza el rating "presentacional" por reputación real. Una reseña por
-- (cancha, autor) → el jugador puede editar la suya (upsert).
-- Ejecutar en Supabase → SQL Editor. IDEMPOTENTE.
-- Multi-país: nada depende del país. RLS del piloto abierto a `anon` (el APK usa
-- la clave anónima); endurecer por auth en una fase posterior.
-- =====================================================================

create table if not exists public.pichangol_resenas (
  id           text        primary key,
  cancha_id    text        not null,
  autor_email  text        not null,
  autor_nombre text        not null default '',
  estrellas    int         not null check (estrellas between 1 and 5),
  comentario   text        not null default '',
  creado       timestamptz not null default now(),
  unique (cancha_id, autor_email)
);

create index if not exists idx_resenas_cancha
  on public.pichangol_resenas (cancha_id);

alter table public.pichangol_resenas enable row level security;

drop policy if exists resenas_lectura on public.pichangol_resenas;
create policy resenas_lectura
  on public.pichangol_resenas for select
  to anon, authenticated using (true);

drop policy if exists resenas_escritura on public.pichangol_resenas;
create policy resenas_escritura
  on public.pichangol_resenas for all
  to anon, authenticated using (true) with check (true);


-- ###################################################################
-- ## supabase_referidos.sql
-- ###################################################################

-- =====================================================================
-- Pichangol · Referidos ("Invita y gana")
-- Un invitado canjea UN código (unique por invitado). El referidor cobra su
-- bono cuando abre su pantalla "Invita y gana" (self-credit vía referidor_dado).
-- Ejecutar en Supabase → SQL Editor. IDEMPOTENTE. RLS del piloto abierto a anon.
-- La app es fail-safe: sin esta tabla, compartir el código funciona pero el
-- canje/atribución no se guarda.
-- =====================================================================

create table if not exists public.pichangol_referidos (
  id              text        primary key,
  invitado_email  text        not null unique,   -- cada persona canjea una vez
  referido_codigo text        not null,          -- código del amigo que lo invitó
  referidor_dado  boolean     not null default false, -- ¿ya se pagó al referidor?
  creado          timestamptz not null default now()
);

create index if not exists idx_referidos_codigo
  on public.pichangol_referidos (referido_codigo);

alter table public.pichangol_referidos enable row level security;

drop policy if exists referidos_lectura on public.pichangol_referidos;
create policy referidos_lectura
  on public.pichangol_referidos for select
  to anon, authenticated using (true);

drop policy if exists referidos_escritura on public.pichangol_referidos;
create policy referidos_escritura
  on public.pichangol_referidos for all
  to anon, authenticated using (true) with check (true);


-- ###################################################################
-- ## supabase_campeonatos.sql
-- ###################################################################

-- =====================================================================
-- Pichangol · Campeonatos de academias (llaves/tabla, inscripción)
-- Ejecutar en Supabase → SQL Editor. Idempotente (se puede correr 2 veces).
--
-- Cada fila = un campeonato completo (columna `data` jsonb con participantes,
-- fixture y resultados). Un solo upsert actualiza todo. Directorio público:
-- cualquiera ve llaves/tabla y se inscribe (motor de crecimiento del app).
-- =====================================================================

create table if not exists public.pichangol_campeonatos (
  id          text primary key,
  academia_id text        not null,
  dueno       text,
  data        jsonb       not null,
  eliminado   boolean     not null default false,
  updated_at  timestamptz not null default now()
);

create index if not exists idx_campeonatos_academia
  on public.pichangol_campeonatos (academia_id);

-- --------------------------------------------------------------------
-- RLS: mismo criterio del piloto que `pichangol_academias` (clave anónima).
-- Lectura/escritura al rol anon. Endurecer por dueño en una fase posterior.
-- --------------------------------------------------------------------
alter table public.pichangol_campeonatos enable row level security;

drop policy if exists campeonatos_lectura on public.pichangol_campeonatos;
create policy campeonatos_lectura
  on public.pichangol_campeonatos for select
  to anon, authenticated
  using (true);

drop policy if exists campeonatos_insert on public.pichangol_campeonatos;
create policy campeonatos_insert
  on public.pichangol_campeonatos for insert
  to anon, authenticated
  with check (true);

drop policy if exists campeonatos_update on public.pichangol_campeonatos;
create policy campeonatos_update
  on public.pichangol_campeonatos for update
  to anon, authenticated
  using (true) with check (true);


-- ###################################################################
-- ## supabase_invitaciones.sql
-- ###################################################################

-- =====================================================================
-- Pichangol · Invitaciones de academia (invitar por correo / teléfono)
-- Ejecutar en Supabase → SQL Editor. Idempotente (se puede correr 2 veces).
--
-- El profe invita a un alumno por CORREO (le aparece sola al entrar a la app,
-- match por email) y/o por TELÉFONO (se entrega por WhatsApp con el código).
-- Cada fila = una invitación (columna `data` jsonb con la Invitacion completa).
-- `academia_id` y `email` van sueltos para filtrar rápido; `estado` para ver
-- pendientes/aceptadas. No se guarda DNI aquí (Ley 29733).
-- =====================================================================

create table if not exists public.pichangol_invitaciones (
  id          text primary key,
  academia_id text        not null,
  email       text,
  estado      text        not null default 'pendiente',
  data        jsonb       not null,
  updated_at  timestamptz not null default now()
);

-- Índices para las dos consultas del app: por academia (profe) y por email
-- (el alumno ve las suyas al entrar con su cuenta de Google).
create index if not exists idx_invitaciones_academia
  on public.pichangol_invitaciones (academia_id);
create index if not exists idx_invitaciones_email
  on public.pichangol_invitaciones (email);

-- --------------------------------------------------------------------
-- RLS: mismo criterio del piloto que `pichangol_matriculas` (el APK usa la
-- clave anónima). Lectura/escritura al rol anon. Endurecer por dueño/alumno
-- en una fase posterior (auth).
-- --------------------------------------------------------------------
alter table public.pichangol_invitaciones enable row level security;

drop policy if exists invitaciones_lectura on public.pichangol_invitaciones;
create policy invitaciones_lectura
  on public.pichangol_invitaciones for select
  to anon, authenticated
  using (true);

drop policy if exists invitaciones_insert on public.pichangol_invitaciones;
create policy invitaciones_insert
  on public.pichangol_invitaciones for insert
  to anon, authenticated
  with check (true);

drop policy if exists invitaciones_update on public.pichangol_invitaciones;
create policy invitaciones_update
  on public.pichangol_invitaciones for update
  to anon, authenticated
  using (true) with check (true);


-- ###################################################################
-- ## supabase_partidos.sql
-- ###################################################################

-- =====================================================================
-- Pichangol · Partidos abiertos ("busca con quién jugar" — el "Match")
-- Ejecutar en Supabase → SQL Editor. IDEMPOTENTE.
--
-- Cualquier jugador publica un partido con cupos; otros se apuntan. El ROSTER y
-- el chat de coordinación REUTILIZAN los grupos (pichangol_grupos +
-- pichangol_grupo_miembros) con el MISMO id del partido — corre antes el SQL de
-- grupos (docs/piloto/supabase_verificacion_grupos_chat.sql).
--
-- RLS del piloto: abierto a anon (el APK usa la clave anónima). Endurecer luego.
-- =====================================================================

create table if not exists public.pichangol_partidos (
  id            text        primary key,
  creador_email text        not null default '',
  creador_nombre text       not null default '',
  deporte       text        not null default 'futbol',
  titulo        text        not null default '',
  fecha         text        not null default '',   -- 'YYYY-MM-DD'
  hora          text        not null default '',   -- 'HH:mm'
  sede_nombre   text        not null default '',
  lat           double precision,
  lng           double precision,
  cupos         integer     not null default 10,
  nota          text        not null default '',
  creado        timestamptz not null default now()
);

create index if not exists idx_partidos_fecha
  on public.pichangol_partidos (fecha, hora);

alter table public.pichangol_partidos enable row level security;

-- Lectura para todos (descubrir partidos cercanos).
drop policy if exists partidos_lectura on public.pichangol_partidos;
create policy partidos_lectura
  on public.pichangol_partidos for select
  to anon, authenticated using (true);

-- Crear/editar/borrar: en el piloto abierto a anon (el creador administra el
-- suyo desde el APK). Endurecer por dueño con auth en una fase posterior.
drop policy if exists partidos_write on public.pichangol_partidos;
create policy partidos_write
  on public.pichangol_partidos for all
  to anon, authenticated using (true) with check (true);


-- ###################################################################
-- ## supabase_bloqueos.sql
-- ###################################################################

-- =====================================================================
-- Pichangol · Horarios bloqueados por el dueño (no reservables)
-- Ejecutar en Supabase → SQL Editor. IDEMPOTENTE.
--
-- El dueño cierra un horario (mantenimiento, walk-in que tomó la cancha, etc.)
-- y ese slot deja de poder reservarse. Clave: (cancha_id, fecha, hora).
-- RLS del piloto: abierto a anon (el APK usa la clave anónima).
-- =====================================================================

create table if not exists public.pichangol_bloqueos (
  cancha_id text        not null,
  fecha     text        not null,  -- 'YYYY-MM-DD'
  hora      text        not null,  -- 'HH:mm'
  creado    timestamptz not null default now(),
  primary key (cancha_id, fecha, hora)
);

alter table public.pichangol_bloqueos enable row level security;

-- Lectura para todos (el jugador ve que el slot no está disponible).
drop policy if exists bloqueos_lectura on public.pichangol_bloqueos;
create policy bloqueos_lectura
  on public.pichangol_bloqueos for select
  to anon, authenticated using (true);

-- Bloquear/desbloquear: en el piloto abierto a anon (el dueño lo hace desde el
-- APK). Endurecer por dueño con auth en una fase posterior.
drop policy if exists bloqueos_write on public.pichangol_bloqueos;
create policy bloqueos_write
  on public.pichangol_bloqueos for all
  to anon, authenticated using (true) with check (true);


-- ###################################################################
-- ## supabase_verificacion_grupos_chat.sql
-- ###################################################################

-- =====================================================================
-- Pichangol · Verificación de jugador + Chat generalizado + Grupos + Buckets
-- Ejecutar en Supabase → SQL Editor. IDEMPOTENTE (se puede correr varias veces).
-- Multi-país: nada aquí depende del país (la verificación es igual en PE/BO/EC).
-- RLS del piloto: el APK usa la clave anónima → se abre a `anon`. Endurecer por
-- auth en una fase posterior. Los documentos personales (Ley 29733) van a un
-- bucket PRIVADO y NUNCA se leen desde el app.
-- =====================================================================


-- =====================================================================
-- 1) VERIFICACIÓN DE JUGADOR  (tabla pichangol_verificaciones)
--    email = PK (el app hace upsert por email). doc/selfie = rutas en el
--    bucket privado `verificacion`. estado: 'no' | 'en_revision' | 'verificado'.
-- =====================================================================
create table if not exists public.pichangol_verificaciones (
  email       text        primary key,
  nombre      text        not null default '',
  doc_path    text        not null default '',
  selfie_path text        not null default '',
  estado      text        not null default 'verificado',
  creado      timestamptz not null default now()
);

alter table public.pichangol_verificaciones enable row level security;

drop policy if exists verif_lectura on public.pichangol_verificaciones;
create policy verif_lectura
  on public.pichangol_verificaciones for select
  to anon, authenticated using (true);

drop policy if exists verif_upsert on public.pichangol_verificaciones;
create policy verif_upsert
  on public.pichangol_verificaciones for all
  to anon, authenticated using (true) with check (true);


-- =====================================================================
-- 2) CHAT GENERALIZADO  (amplía pichangol_mensajes: cancha/grupo + fotos)
--    Si la tabla ya existe (chat de academia), solo se AGREGAN columnas y se
--    hace academia_id nullable. Si es proyecto nuevo, se crea completa.
-- =====================================================================
create table if not exists public.pichangol_mensajes (
  id           text        primary key,
  hilo         text        not null,
  tipo         text        not null default 'academia', -- academia | cancha | grupo
  ref_id       text        not null default '',         -- academiaId | canchaId | grupoId
  academia_id  text,                                     -- solo academia (nullable)
  cuenta_email text        not null default '',
  autor_email  text        not null default '',
  autor_nombre text        not null default '',
  es_profe     boolean     not null default false,
  texto        text        not null default '',
  media_url    text        not null default '',          -- foto adjunta ('' = solo texto)
  creado       timestamptz not null default now()
);

-- Columnas nuevas para instalaciones que ya tenían la tabla del chat de academia.
alter table public.pichangol_mensajes
  add column if not exists tipo      text not null default 'academia';
alter table public.pichangol_mensajes
  add column if not exists ref_id    text not null default '';
alter table public.pichangol_mensajes
  add column if not exists media_url text not null default '';

-- Los mensajes de cancha/grupo NO traen academia_id: hazlo nullable.
alter table public.pichangol_mensajes alter column academia_id drop not null;

create index if not exists idx_mensajes_hilo
  on public.pichangol_mensajes (hilo, creado);
create index if not exists idx_mensajes_ref
  on public.pichangol_mensajes (tipo, ref_id, creado);

-- Realtime (idempotente).
do $$
begin
  begin
    alter publication supabase_realtime add table public.pichangol_mensajes;
  exception when duplicate_object then null;
  end;
end $$;

alter table public.pichangol_mensajes enable row level security;

drop policy if exists mensajes_lectura on public.pichangol_mensajes;
create policy mensajes_lectura
  on public.pichangol_mensajes for select
  to anon, authenticated using (true);

drop policy if exists mensajes_insert on public.pichangol_mensajes;
create policy mensajes_insert
  on public.pichangol_mensajes for insert
  to anon, authenticated with check (true);


-- =====================================================================
-- 3) GRUPOS DE CHAT  (pichangol_grupos + pichangol_grupo_miembros)
--    Los mensajes del grupo viven en pichangol_mensajes (tipo='grupo').
-- =====================================================================
create table if not exists public.pichangol_grupos (
  id            text        primary key,
  nombre        text        not null default '',
  creador_email text        not null default '',
  creado        timestamptz not null default now()
);

create table if not exists public.pichangol_grupo_miembros (
  grupo_id text not null,
  email    text not null,
  nombre   text not null default '',
  primary key (grupo_id, email)
);

create index if not exists idx_grupo_miembros_email
  on public.pichangol_grupo_miembros (email);

alter table public.pichangol_grupos          enable row level security;
alter table public.pichangol_grupo_miembros  enable row level security;

drop policy if exists grupos_all on public.pichangol_grupos;
create policy grupos_all
  on public.pichangol_grupos for all
  to anon, authenticated using (true) with check (true);

drop policy if exists grupo_miembros_all on public.pichangol_grupo_miembros;
create policy grupo_miembros_all
  on public.pichangol_grupo_miembros for all
  to anon, authenticated using (true) with check (true);


-- =====================================================================
-- 4) BUCKETS DE STORAGE
--    `verificacion` → PRIVADO (documentos, Ley 29733): solo subir, no leer.
--    `chat`         → PÚBLICO (fotos del chat): subir + leer (getPublicUrl).
-- =====================================================================
insert into storage.buckets (id, name, public)
  values ('verificacion', 'verificacion', false)
  on conflict (id) do nothing;

insert into storage.buckets (id, name, public)
  values ('chat', 'chat', true)
  on conflict (id) do nothing;

-- verificacion: el APK (anon) SOLO sube. Nadie lee desde el app (privado).
drop policy if exists verif_bucket_insert on storage.objects;
create policy verif_bucket_insert
  on storage.objects for insert
  to anon, authenticated
  with check (bucket_id = 'verificacion');

-- chat: subir y leer (bucket público, para mostrar la foto en el chat).
drop policy if exists chat_bucket_insert on storage.objects;
create policy chat_bucket_insert
  on storage.objects for insert
  to anon, authenticated
  with check (bucket_id = 'chat');

drop policy if exists chat_bucket_select on storage.objects;
create policy chat_bucket_select
  on storage.objects for select
  to anon, authenticated
  using (bucket_id = 'chat');

-- =====================================================================
-- LISTO. Después de correr esto:
--   • La verificación de jugador ya guarda de verdad (tabla + bucket privado).
--   • El chat soporta cancha/grupo y fotos.
--   • Recuerda tener desplegada la Edge Function `push-mensaje` (rama grupo)
--     y el webhook/trigger de INSERT en pichangol_mensajes (ver
--     docs/piloto/supabase_mensajes.sql y docs/piloto/push_fcm_setup.md).
-- =====================================================================
