-- OPERACIÓN DE LA ACADEMIA: MISMOS DATOS EN EL APP Y EN LA WEB.
-- ----------------------------------------------------------------------------
-- Requiere antes `docs/piloto/supabase_academia_operacion.sql` (ya corrido en
-- QAS y PRD): crea asistencias, evaluaciones y bitácora con RLS SIN políticas
-- (solo el backend web, rol postgres, podía usarlas).
--
-- Este script:
--   1) crea `pichangol_academia_planes` = los PLANES DE TRABAJO del profe
--      (`PlanTrabajo.toJson` del app en `data`), que antes vivían solo en el
--      teléfono; la web evalúa sobre ellos (fallback: plantilla del deporte);
--   2) abre las 4 tablas al APK (llave anon / authenticated) con el MISMO
--      criterio del piloto que `pichangol_academias` y `pichangol_matriculas`
--      (políticas permisivas; se endurecen por dueño cuando haya auth real).
--      El backend web no se ve afectado (entra como postgres, dueño).
--
-- Correr a mano en Supabase → SQL Editor: QAS ("Pichangol") y, con
-- autorización del director, PCG-PRD. Idempotente.

-- === 1) Planes de trabajo ====================================================
create table if not exists public.pichangol_academia_planes (
  id          text primary key,               -- 'plan_<µs>' (PlanTrabajo.id)
  academia_id text        not null,
  data        jsonb       not null,           -- PlanTrabajo.toJson
  eliminado   boolean     not null default false, -- borrado lógico (sincroniza el borrado entre equipos)
  actualizado timestamptz not null default now()
);
create index if not exists pichangol_academia_planes_ac
  on public.pichangol_academia_planes (academia_id);

-- === 2) RLS: lectura/escritura para el APK (piloto) ==========================
alter table public.pichangol_academia_asistencias enable row level security;
alter table public.pichangol_academia_evaluaciones enable row level security;
alter table public.pichangol_academia_notas       enable row level security;
alter table public.pichangol_academia_planes      enable row level security;

drop policy if exists academia_asistencias_todo on public.pichangol_academia_asistencias;
create policy academia_asistencias_todo
  on public.pichangol_academia_asistencias
  for all to anon, authenticated
  using (true) with check (true);

drop policy if exists academia_evaluaciones_todo on public.pichangol_academia_evaluaciones;
create policy academia_evaluaciones_todo
  on public.pichangol_academia_evaluaciones
  for all to anon, authenticated
  using (true) with check (true);

drop policy if exists academia_notas_todo on public.pichangol_academia_notas;
create policy academia_notas_todo
  on public.pichangol_academia_notas
  for all to anon, authenticated
  using (true) with check (true);

drop policy if exists academia_planes_todo on public.pichangol_academia_planes;
create policy academia_planes_todo
  on public.pichangol_academia_planes
  for all to anon, authenticated
  using (true) with check (true);

-- === 3) Verificación =========================================================
select tablename, policyname, cmd
  from pg_policies
 where tablename in ('pichangol_academia_asistencias', 'pichangol_academia_evaluaciones',
                     'pichangol_academia_notas', 'pichangol_academia_planes')
 order by tablename, policyname;
