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
