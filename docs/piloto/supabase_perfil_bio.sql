-- ============================================================================
-- Pichangol · BIO del perfil (campos estilo Airbnb: "Mi cancha favorita",
-- "Me dedico a", "Mi mayor logro deportivo", etc.)
-- ----------------------------------------------------------------------------
-- Un solo JSONB flexible: {"cancha_favorita":"...", "dedico":"...", ...}.
-- Lo edita el dueño del perfil desde "Editar perfil" y se muestra donde el
-- perfil es público (chat, ranking, retos).
--
-- Correr en Supabase → SQL Editor del proyecto del piloto. Idempotente.
-- ============================================================================

alter table public.pichangol_perfiles
  add column if not exists bio jsonb;
