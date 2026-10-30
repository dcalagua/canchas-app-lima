-- CanchaLibre · 0006 · "CADA UNO PAGA SU PARTE" (dividir el pago de una
-- reserva web entre amigos; ronda 3 de la web, oct-2026).
--
-- El organizador aparta los turnos (hold largo, `medio_pago = 'division'`) y
-- comparte un enlace `/dividir/{token}`. Cada amigo paga UNA parte con los
-- medios DEL CLUB (su Culqi o un voucher que el club aprueba): el dinero va
-- directo al club. Cuando TODAS las partes están pagadas la reserva se
-- confirma como cualquier reserva de cobro directo (una sola comisión sobre el
-- total). Si vence sin completarse, el horario se suelta y cada parte pagada
-- se devuelve (Culqi del club por API; vouchers → el club devuelve a mano).
--
-- Solo el backend (rol postgres) lee/escribe: RLS activo y SIN políticas → la
-- anon key no ve nada. Idempotente.

create table if not exists public.cl_division_pago (
  id                  text primary key,             -- div_<ms>_<hex>
  token               text not null unique,         -- va en el enlace: no adivinable
  reserva_ref         text not null,                -- grupo_reserva_id o id de la 1.ª fila
  reserva_ids         jsonb not null default '[]'::jsonb,
  cancha_id           text not null,
  dueno               text not null,                -- correo del dueño del club (minúsculas)
  organizador_email   text not null,
  organizador_nombre  text not null default '',
  moneda              text not null default 'PEN',  -- ISO de la cancha
  total_centimos      bigint not null check (total_centimos > 0),
  partes              integer not null check (partes between 2 and 12),
  parte_centimos      bigint not null check (parte_centimos > 0),  -- lo que paga cada amigo
  estado              text not null default 'abierta'
                      check (estado in ('abierta', 'completa', 'confirmada', 'vencida', 'cancelada')),
  motivo              text not null default '',
  vence_en            timestamptz not null,
  aviso_en            timestamptz,                  -- cuándo se avisó al organizador "faltan partes"
  creado_en           timestamptz not null default now(),
  cerrado_en          timestamptz
);
-- Una sola división VIVA por bloque de reserva.
create unique index if not exists uq_cl_div_ref_viva on public.cl_division_pago (reserva_ref)
  where estado in ('abierta', 'completa', 'confirmada');
create index if not exists idx_cl_div_estado_vence on public.cl_division_pago (estado, vence_en);
create index if not exists idx_cl_div_org on public.cl_division_pago (lower(organizador_email));
alter table public.cl_division_pago enable row level security;

create table if not exists public.cl_division_partes (
  id                text primary key,               -- <division_id>_<n>
  division_id       text not null references public.cl_division_pago (id) on delete cascade,
  n                 integer not null check (n between 0 and 11),   -- 0 = la del organizador (lleva el resto de céntimos)
  monto_centimos    bigint not null check (monto_centimos > 0),
  estado            text not null default 'libre'
                    check (estado in ('libre', 'cobrando', 'en_revision', 'pagada',
                                      'devolver', 'reembolsada', 'devuelta', 'no_recibido')),
  pagador_email     text not null default '',
  pagador_nombre    text not null default '',
  por_organizador   boolean not null default false, -- la cubrió el organizador con "Pagar lo que falta"
  medio             text not null default '',       -- yape | tarjeta | voucher_<medio>
  cobro_id          text not null default '',       -- chr_…#n (Culqi del club) o pm:<voucher>
  pago_manual_id    text not null default '',       -- voucher en cl_pagos_manuales (si lo hubo)
  refund_id         text not null default '',
  devolver_centimos bigint not null default 0 check (devolver_centimos >= 0),  -- cuánto se le debe devolver
  nota              text not null default '',       -- por qué se devuelve (vencida, cancelada, voucher sin revisar…)
  tomada_en         timestamptz,
  pagada_en         timestamptz,
  resuelta_en       timestamptz,                    -- devolución resuelta (reembolsada / devuelta / no_recibido)
  actualizado_en    timestamptz not null default now(),
  unique (division_id, n)
);
-- Un mismo cobro jamás paga dos partes.
create unique index if not exists uq_cl_divp_cobro on public.cl_division_partes (cobro_id) where cobro_id <> '';
-- Cada AMIGO paga a lo sumo una parte viva de la división (el organizador
-- puede cubrir varias con "Pagar lo que falta": esas van con por_organizador).
create unique index if not exists uq_cl_divp_pagador on public.cl_division_partes (division_id, lower(pagador_email))
  where pagador_email <> '' and not por_organizador and estado in ('cobrando', 'en_revision', 'pagada');
create index if not exists idx_cl_divp_div on public.cl_division_partes (division_id, estado);
create index if not exists idx_cl_divp_pagador on public.cl_division_partes (lower(pagador_email)) where pagador_email <> '';
create index if not exists idx_cl_divp_pm on public.cl_division_partes (pago_manual_id) where pago_manual_id <> '';
alter table public.cl_division_partes enable row level security;

insert into public.cl_schema_migraciones (version, descripcion)
values ('0006', 'dividir el pago de una reserva web entre amigos (pago directo al club)')
on conflict (version) do nothing;
