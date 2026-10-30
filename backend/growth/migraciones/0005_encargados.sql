-- CanchaLibre · 0005 · ENCARGADOS DEL LOCAL (rol único "Recepción").
--
-- El DUEÑO de un local invita a una persona por su correo de Google para que
-- le ayude a operarlo. Rol `recepcion`: ve Hoy / Calendario / Reservas de las
-- canchas de ESE local, registra reservas manuales, bloquea turnos, marca
-- pagos y aprueba o rechaza los comprobantes (Pagos por confirmar). NO ve
-- plata (ingresos, billetera, reportes, liquidaciones), no edita precios,
-- reglas, fotos ni datos del local, no toca la cuenta Culqi ni los medios de
-- pago, no invita a otros y no cancela con devolución. La autorización la
-- decide SOLO el backend (`web/permisos.py`).
--
-- El alcance es el LOCAL (`local_key` = "dueño|club", el mismo de la tarjeta
-- de fidelidad) + las canchas que tenía al invitar (`cancha_ids`, ancla: si el
-- dueño renombra el local, el encargo sigue). Una cancha que deja de ser del
-- dueño sale sola del alcance (se resuelve contra `pichangol_canchas.dueno`).
--
-- Solo el backend (rol postgres) lee/escribe: RLS activo y SIN políticas → la
-- anon key del APK no ve estas tablas. Idempotente.

create table if not exists public.cl_encargados (
  id             text primary key,                 -- enc_<µs>
  dueno          text not null,                    -- correo del dueño (minúsculas)
  local_key      text not null,                    -- "dueño|club" (fidelidad.local_key)
  local_nombre   text not null default '',
  cancha_ids     jsonb not null default '[]'::jsonb,
  email          text not null,                    -- correo de Google del encargado (minúsculas)
  rol            text not null default 'recepcion' check (rol in ('recepcion')),
  estado         text not null default 'invitado'
                 check (estado in ('invitado', 'activo', 'rechazado', 'revocado')),
  invitado_por   text not null default '',
  creado         timestamptz not null default now(),
  aceptado_en    timestamptz,
  revocado_en    timestamptz,
  actualizado_en timestamptz not null default now()
);
-- Una sola invitación VIVA por persona y local (reinvitar tras revocar crea otra fila).
create unique index if not exists uq_cl_enc_vivo on public.cl_encargados (local_key, email)
  where estado in ('invitado', 'activo');
create index if not exists idx_cl_enc_email on public.cl_encargados (email)
  where estado in ('invitado', 'activo');
create index if not exists idx_cl_enc_dueno on public.cl_encargados (dueno);
alter table public.cl_encargados enable row level security;

-- Bitácora: qué hizo cada encargado (reserva manual, bloqueo, pago marcado,
-- comprobante aprobado/rechazado, no-show, reserva quitada). El dueño la ve en
-- su página de Encargados. Las acciones del propio dueño no se registran aquí.
create table if not exists public.cl_encargados_acciones (
  id           bigserial primary key,
  encargado_id text not null default '',
  dueno        text not null,
  actor        text not null,
  accion       text not null,
  cancha_id    text not null default '',
  ref          text not null default '',
  detalle      jsonb not null default '{}'::jsonb,
  creado_en    timestamptz not null default now()
);
create index if not exists idx_cl_enc_acc_dueno on public.cl_encargados_acciones (dueno, creado_en desc);
alter table public.cl_encargados_acciones enable row level security;

insert into public.cl_schema_migraciones (version, descripcion)
values ('0005', 'encargados del local (rol recepcion) + bitácora de sus acciones')
on conflict (version) do nothing;
