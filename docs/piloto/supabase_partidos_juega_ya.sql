-- =====================================================================
-- Pichangol · JUEGA YA (fases 1 y 2): partidos y "Busco partner" con
-- tipo, modalidad, nivel, etiquetas y cancha. IDEMPOTENTE.
-- Correr en Supabase → SQL Editor en QAS ("Pichangol") y, con autorización
-- del director, en PCG-PRD.
--
-- · tipo       'partido' (completar equipo) | 'partner' (tenis/pickleball)
-- · modalidad  partner: 'singles' | 'dobles' | 'pelotear' ('' en partidos)
-- · nivel      '' (todos) | 'inicial' | 'intermedio' | 'avanzado' | 'competitivo'
-- · etiquetas  ["cancha_reservada", "se_divide", "traer_pechera", …] (juego.py)
-- · cancha_id  local de Pichangol donde se juega (para "Ver cancha")
--
-- Sin este SQL la web y el APK siguen funcionando como antes (sin esos datos).
-- Los APK anteriores siguen publicando: sus filas toman los valores por defecto.
-- El índice por `creado` lo usa el barrido de avisos de partidos cerca.
-- =====================================================================

alter table public.pichangol_partidos
  add column if not exists tipo      text  not null default 'partido',
  add column if not exists modalidad text  not null default '',
  add column if not exists nivel     text  not null default '',
  add column if not exists etiquetas jsonb not null default '[]'::jsonb,
  add column if not exists cancha_id text;

create index if not exists idx_partidos_creado
  on public.pichangol_partidos (creado);

create index if not exists idx_partidos_tipo_fecha
  on public.pichangol_partidos (tipo, fecha);
