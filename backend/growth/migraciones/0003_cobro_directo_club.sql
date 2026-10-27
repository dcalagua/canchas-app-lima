-- CanchaLibre · 0003 · COBRO DIRECTO AL CLUB (plan nocturno A4 + A5).
-- Decisión del usuario (26-oct-2026): el dinero de la reserva va DIRECTO al
-- club. Cada club (su dueño) configura:
--   * su PROPIA cuenta Culqi (llave pública + secreta cifrada con Fernet,
--     PAGOS_ENC_KEY; la secreta jamás sale del backend), y
--   * sus medios MANUALES (Yape, Plin, transferencia, billeteras/QR) que el
--     jugador ve en el checkout para pagar y subir su voucher.
-- Solo el backend (rol postgres) lee/escribe estas tablas: RLS activo y SIN
-- políticas → la anon key del APK no las ve. Idempotente.

create table if not exists public.cl_pasarela_club (
  dueno              text primary key,             -- correo del dueño (minúsculas)
  proveedor          text not null default 'culqi',
  public_key         text not null,
  secret_key_cifrada text not null,
  secret_key_ult4    text not null default '',
  modo               text not null default 'test' check (modo in ('test', 'live')),
  webhook_ref        text not null unique,         -- id opaco para la URL del webhook del club
  activo             boolean not null default true,
  verificada         boolean not null default false,  -- Culqi aceptó la llave al guardarla
  actualizado_en     timestamptz not null default now()
);
alter table public.cl_pasarela_club enable row level security;

create table if not exists public.cl_medios_pago_club (
  id             bigserial primary key,
  dueno          text not null,
  tipo           text not null check (tipo in ('yape', 'plin', 'transferencia', 'billetera', 'qr')),
  titular        text not null default '',
  numero         text not null default '',   -- celular de Yape/Plin o de la billetera
  banco          text not null default '',
  cuenta         text not null default '',
  cci            text not null default '',
  qr_url         text not null default '',
  nota           text not null default '',
  activo         boolean not null default true,
  orden          integer not null default 0,
  actualizado_en timestamptz not null default now()
);
create index if not exists idx_cl_medios_dueno on public.cl_medios_pago_club (dueno) where activo;
alter table public.cl_medios_pago_club enable row level security;

-- Pagos MANUALES de reservas (voucher). Un registro por bloque de reserva.
create table if not exists public.cl_pagos_manuales (
  id              text primary key,             -- pgm_<ms>_<n>
  reserva_ref     text not null,                -- grupo_reserva_id o id de la 1.ª fila
  reserva_ids     jsonb not null default '[]'::jsonb,
  cancha_id       text not null,
  dueno           text not null,
  jugador_email   text not null,
  jugador_nombre  text not null default '',
  monto_centimos  bigint not null check (monto_centimos > 0),
  moneda          text not null default 'PEN',
  medio           text not null,                -- yape | plin | transferencia | billetera | qr
  operacion       text not null default '',     -- nº de operación / código de seguridad (normalizado)
  -- La imagen del voucher es DATO PERSONAL (Ley 29733): se guarda aquí, privada,
  -- comprimida (≤ 1600 px, JPEG), y solo el dueño de la cancha la ve por el
  -- backend. Nunca en un bucket público.
  voucher_img     bytea,
  voucher_mime    text not null default '',
  voucher_hash    text not null default '',     -- sha256 de la imagen (voucher reciclado)
  estado          text not null default 'en_revision'
                  check (estado in ('en_revision', 'aprobado', 'rechazado', 'vencido')),
  motivo_rechazo  text not null default '',
  vence_en        timestamptz not null,
  creado_en       timestamptz not null default now(),
  resuelto_en     timestamptz,
  resuelto_por    text not null default ''
);
create unique index if not exists uq_cl_pm_reserva_viva on public.cl_pagos_manuales (reserva_ref)
  where estado in ('en_revision', 'aprobado');
-- Anti-fraude: el MISMO nº de operación o la MISMA imagen no pagan dos reservas del club.
create unique index if not exists uq_cl_pm_operacion on public.cl_pagos_manuales (dueno, medio, operacion)
  where operacion <> '' and estado in ('en_revision', 'aprobado');
create unique index if not exists uq_cl_pm_voucher on public.cl_pagos_manuales (dueno, voucher_hash)
  where voucher_hash <> '' and estado in ('en_revision', 'aprobado');
create index if not exists idx_cl_pm_dueno_estado on public.cl_pagos_manuales (dueno, estado);
create index if not exists idx_cl_pm_vence on public.cl_pagos_manuales (vence_en) where estado = 'en_revision';
alter table public.cl_pagos_manuales enable row level security;

insert into public.cl_schema_migraciones (version, descripcion)
values ('0003', 'cobro directo al club: pasarela propia, medios manuales, vouchers')
on conflict (version) do nothing;
