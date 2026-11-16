-- CanchaLibre · 0007 · "CADA UNO PAGA SU PARTE": devoluciones a prueba de
-- reintentos (revisión independiente del pago dividido, oct-2026).
--
-- 1. `cl_division_cargos_devueltos`: cada cargo de Culqi DEL CLUB que ya se
--    devolvió (entero o en parte). Un webhook tardío de ese cargo se ignora
--    (no vuelve a pagar una parte que alguien retomó) y un barrido que se
--    reanuda tras un error no lo devuelve dos veces.
-- 2. `cl_division_tardios`: comprobantes que un amigo subió cuando su parte ya
--    no estaba reservada para él (la toma de 15 min venció o la división se
--    cerró) pero que YA pagó al club por Yape/Plin/transferencia. No pagan
--    ninguna parte: el club los revisa en Pagos por confirmar y, si el dinero
--    llegó (o venció sin revisar), quedan en Devoluciones.
--
-- Solo el backend (rol postgres) lee/escribe: RLS activo y SIN políticas.
-- Idempotente.

create table if not exists public.cl_division_cargos_devueltos (
  charge_id       text primary key,                 -- chr_… (sin el sufijo #n)
  division_id     text not null default '',
  monto_centimos  bigint not null default 0 check (monto_centimos >= 0),
  refund_id       text not null default '',
  motivo          text not null default '',
  creado_en       timestamptz not null default now()
);
alter table public.cl_division_cargos_devueltos enable row level security;

create table if not exists public.cl_division_tardios (
  id                text primary key,               -- dvt_<ms>_<hex>
  division_id       text not null references public.cl_division_pago (id) on delete cascade,
  n                 integer not null default 0,     -- parte que intentó pagar (solo para mostrar)
  pagador_email     text not null,
  pagador_nombre    text not null default '',
  monto_centimos    bigint not null check (monto_centimos > 0),
  medio             text not null default '',       -- voucher_<medio>
  pago_manual_id    text not null default '',       -- su comprobante en cl_pagos_manuales
  estado            text not null default 'en_revision'
                    check (estado in ('en_revision', 'devolver', 'devuelta', 'no_recibido', 'rechazado')),
  nota              text not null default '',       -- toma_vencida | division_cerrada · aprobado_tarde | sin_revisar
  creado_en         timestamptz not null default now(),
  resuelta_en       timestamptz
);
create index if not exists idx_cl_divt_pm on public.cl_division_tardios (pago_manual_id) where pago_manual_id <> '';
create index if not exists idx_cl_divt_div on public.cl_division_tardios (division_id, estado);
alter table public.cl_division_tardios enable row level security;

insert into public.cl_schema_migraciones (version, descripcion)
values ('0007', 'pago dividido: cargos devueltos y comprobantes tardíos')
on conflict (version) do nothing;
