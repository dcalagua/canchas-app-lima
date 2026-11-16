-- =====================================================================
-- Pichangol · Nivel de jugador (estilo Playtomic 0-7, aquí 1.0–7.0)
-- Ejecutar en Supabase → SQL Editor. IDEMPOTENTE.
--
-- El nivel se siembra en el onboarding (auto-cuestionario) y se AJUSTA con los
-- resultados reales (retos, campeonatos) mediante un ELO suave en el APK. Es por
-- DEPORTE (un jugador puede ser 5.0 en fútbol y 3.0 en tenis).
-- Clave: (email, deporte).
-- RLS del piloto: abierto a anon (el APK usa la clave anónima).
-- =====================================================================

create table if not exists public.pichangol_niveles (
  email         text        not null,
  deporte       text        not null,   -- 'futbol' | 'tenis' | 'padel' | ...
  nivel         real        not null default 3.0,   -- 1.0 .. 7.0
  partidos      integer     not null default 0,
  victorias     integer     not null default 0,
  confiabilidad real        not null default 1.0,    -- 0.0 .. 1.0 (asistencia)
  actualizado   timestamptz not null default now(),
  primary key (email, deporte)
);

-- Ranking/matchmaking por deporte y nivel (buscar parejos rápido).
create index if not exists pichangol_niveles_deporte_nivel
  on public.pichangol_niveles (deporte, nivel);

alter table public.pichangol_niveles enable row level security;

-- Lectura para todos (ver el nivel en el perfil/ranking/matchmaking).
drop policy if exists niveles_lectura on public.pichangol_niveles;
create policy niveles_lectura
  on public.pichangol_niveles for select
  to anon, authenticated using (true);

-- Escritura: en el piloto abierto a anon (el APK actualiza el nivel del jugador).
-- Endurecer por dueño del registro (email = auth) en una fase posterior.
drop policy if exists niveles_write on public.pichangol_niveles;
create policy niveles_write
  on public.pichangol_niveles for all
  to anon, authenticated using (true) with check (true);
