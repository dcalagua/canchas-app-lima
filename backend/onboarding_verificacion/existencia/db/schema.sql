-- Esquema del submódulo VERIFICACION DE EXISTENCIA (Pichangol)
-- Principio: VERIFICAR Y NO RETENER (Ley 29733 + DS 016-2024-JUS).
--
-- PROHIBIDO por diseño (NO crear estas columnas en ninguna tabla):
--   * imágenes de DNI / recibo / selfie (ni binarios ni URLs)
--   * número de DNI en claro
--   * domicilio fiscal en claro persistido como dato del titular
-- Los documentos personales se procesan en memoria/temporal y se ELIMINAN.
-- Aquí solo persiste el RESULTADO (bool + score + fecha) y las evidencias NO
-- personales (factores y sus puntajes).

-- =========================================================================
-- 1) Resultados de verificación (lo único que se conserva del proceso)
-- =========================================================================
create table if not exists verificaciones (
  id              bigserial primary key,
  cancha_id       text        not null,
  score_existencia int        not null check (score_existencia between 0 and 100),
  aprobado        boolean     not null,
  nivel           text        not null check (nivel in ('alto','medio','bajo')),
  -- evidencias: SOLO factores y sus puntajes (sin datos personales)
  evidencias      jsonb       not null default '[]'::jsonb,
  fuente_sunat    text,                 -- p.ej. 'factiliza-stub' (trazabilidad)
  fecha           timestamptz not null default now(),
  -- TTL de eliminación del resultado (housekeeping lo purga al vencer)
  eliminar_despues timestamptz
);
create index if not exists idx_verificaciones_cancha on verificaciones (cancha_id);

-- =========================================================================
-- 2) Consentimientos (verificacion | marketing | llamada)
-- =========================================================================
create table if not exists consentimientos (
  id              bigserial primary key,
  sujeto_id       text        not null,   -- dueño/cancha (identificador, no DNI)
  tipo            text        not null check (tipo in ('verificacion','marketing','llamada')),
  otorgado        boolean     not null,
  canal           text,                   -- app | whatsapp | web | presencial
  base_legal      text,                   -- p.ej. 'Art. 5 Ley 29733'
  fecha           timestamptz not null default now(),
  vigencia_hasta  timestamptz,            -- null si fue denegado
  unique (sujeto_id, tipo)
);
create index if not exists idx_consent_sujeto on consentimientos (sujeto_id);

-- Recontacto (marketing/llamada): permitido SOLO si existe consentimiento
-- otorgado y vigente para ese sujeto y tipo. Si se denegó o venció, se bloquea.
