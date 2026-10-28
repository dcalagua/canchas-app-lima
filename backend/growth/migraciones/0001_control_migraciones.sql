-- CanchaLibre · 0001 · Control de migraciones versionadas.
-- Registra qué migración corrió en cada base (QAS / PRD / local). Idempotente.
create table if not exists public.cl_schema_migraciones (
  version     text primary key,
  descripcion text not null default '',
  aplicada_en timestamptz not null default now()
);
alter table public.cl_schema_migraciones enable row level security;
-- Sin políticas: solo el backend (rol postgres) la lee/escribe; anon no la ve.
insert into public.cl_schema_migraciones (version, descripcion)
values ('0001', 'control de migraciones') on conflict (version) do nothing;
