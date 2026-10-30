-- Presencia / "última vez en línea" (Pichangol) — estilo WhatsApp.
-- Cada usuario (correo) tiene UNA fila con la última vez que estuvo activo en la
-- app. El cliente hace upsert de su propia fila cada ~25 s mientras la app está
-- en primer plano (y al minimizar). Para mostrar el estado de un contacto se lee
-- su `visto_en`: si es de hace < ~40 s → "en línea"; si no → "última vez …".
--
-- Correr en: Supabase → SQL Editor (proyecto del piloto).

create table if not exists public.pichangol_presencia (
  email     text primary key,
  visto_en  timestamptz not null default now()
);

alter table public.pichangol_presencia enable row level security;

-- Lectura pública (para ver el estado de un contacto) y upsert de la propia fila.
-- Piloto: políticas abiertas (como el resto de tablas del piloto). Endurecer en
-- PROD (que cada quien solo escriba su propia fila).
drop policy if exists presencia_sel on public.pichangol_presencia;
create policy presencia_sel on public.pichangol_presencia
  for select using (true);

drop policy if exists presencia_ins on public.pichangol_presencia;
create policy presencia_ins on public.pichangol_presencia
  for insert with check (true);

drop policy if exists presencia_upd on public.pichangol_presencia;
create policy presencia_upd on public.pichangol_presencia
  for update using (true) with check (true);
