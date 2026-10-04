-- Ubicación EN TIEMPO REAL en el chat (Pichangol) — estilo WhatsApp.
-- Una fila por (hilo, correo): mientras alguien comparte su ubicación en vivo,
-- su dispositivo hace upsert de su posición cada ~8 s hasta `expira_en`. El otro
-- lado la relee (poll cada ~5 s) para ver el pin moverse y abrir el mapa con la
-- posición más reciente. "Detener" pone `expira_en = now()`.
--
-- No guarda historial de recorrido (solo la última posición) → privacidad y
-- costo mínimos. Correr en: Supabase → SQL Editor (proyecto del piloto).

create table if not exists public.pichangol_ubicacion_vivo (
  hilo           text        not null,
  email          text        not null,
  lat            double precision not null,
  lng            double precision not null,
  actualizado_en timestamptz not null default now(),
  expira_en      timestamptz not null,
  primary key (hilo, email)
);

-- Búsqueda por hilo (el lector filtra por hilo + email del autor).
create index if not exists idx_ubic_vivo_hilo
  on public.pichangol_ubicacion_vivo (hilo);

alter table public.pichangol_ubicacion_vivo enable row level security;

-- Piloto: políticas abiertas (como el resto de tablas del piloto). Endurecer en
-- PROD (que cada quien solo escriba su propia fila / lea solo sus hilos).
drop policy if exists ubic_vivo_sel on public.pichangol_ubicacion_vivo;
create policy ubic_vivo_sel on public.pichangol_ubicacion_vivo
  for select using (true);

drop policy if exists ubic_vivo_ins on public.pichangol_ubicacion_vivo;
create policy ubic_vivo_ins on public.pichangol_ubicacion_vivo
  for insert with check (true);

drop policy if exists ubic_vivo_upd on public.pichangol_ubicacion_vivo;
create policy ubic_vivo_upd on public.pichangol_ubicacion_vivo
  for update using (true) with check (true);
